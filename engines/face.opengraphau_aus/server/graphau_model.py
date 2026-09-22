"""ME-GraphAU / OpenGraphAU, stage 2 (MEFL), ResNet-50 backbone — inference only.

Derived from https://github.com/lingjivoo/OpenGraphAU at commit
a0ad10d516ed121f476cbc6d66a84ebfc033a53f (2025-08-21), files model/MEFL.py,
model/resnet.py, model/graph.py, model/graph_edge_model.py and
model/basic_block.py.

    Copyright the OpenGraphAU authors (Luo, Song, Xie, Shen, Gunes).
    Licensed under the Apache License, Version 2.0. You may obtain a copy at
    http://www.apache.org/licenses/LICENSE-2.0 — distributed on an "AS IS"
    BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

Modifications, as Apache-2.0 §4(b) requires them to be stated:

- Only the stage-2 (MEFL) head and the ResNet-50 backbone are kept. The Swin
  backbones, the stage-1 (ANFL) head, and all training code are removed.
- The backbone no longer loads ImageNet weights from a relative
  `pretrain_models/` directory on construction. Every weight comes from the
  released checkpoint, which is loaded STRICTLY by the engine.
- `torch.autograd.Variable` edge matrices became non-persistent buffers, so they
  follow the module across devices and stay out of the state dict (the released
  checkpoint does not contain them).

Parameter and module names are otherwise unchanged. They have to be: they are
the keys of the released state dict, and the engine's strict load is what proves
the two still match.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

#: Output order of the released checkpoints: 27 bilateral AUs, then 14
#: lateralised ones as (left, right) pairs of AU 1, 2, 4, 6, 10, 12, 14.
#: From upstream tool/dataset_process.py; the 41-wide output has no labels of
#: its own, so this list IS the meaning of each column.
MAIN_AUS = ("1", "2", "4", "5", "6", "7", "9", "10", "11", "12", "13", "14",
            "15", "16", "17", "18", "19", "20", "22", "23", "24", "25", "26",
            "27", "32", "38", "39")
LATERAL_AUS = ("L1", "R1", "L2", "R2", "L4", "R4", "L6", "R6", "L10", "R10",
               "L12", "R12", "L14", "R14")


# ---------------------------------------------------------------------------
# basic_block.py
# ---------------------------------------------------------------------------

def bn_init(bn):
    bn.weight.data.fill_(1)
    bn.bias.data.zero_()


class LinearBlock(nn.Module):
    def __init__(self, in_features, out_features=None, drop=0.0):
        super().__init__()
        out_features = out_features or in_features
        self.fc = nn.Linear(in_features, out_features)
        self.bn = nn.BatchNorm1d(out_features)
        self.relu = nn.ReLU(inplace=True)
        self.drop = nn.Dropout(drop)
        self.fc.weight.data.normal_(0, math.sqrt(2. / out_features))
        self.bn.weight.data.fill_(1)
        self.bn.bias.data.zero_()

    def forward(self, x):
        x = self.drop(x)
        x = self.fc(x).permute(0, 2, 1)
        x = self.relu(self.bn(x)).permute(0, 2, 1)
        return x


# ---------------------------------------------------------------------------
# resnet.py (ResNet-50 only)
# ---------------------------------------------------------------------------

class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super().__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes * 4)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        if self.downsample is not None:
            residual = self.downsample(x)
        out += residual
        return self.relu(out)


class ResNet(nn.Module):
    def __init__(self, block, layers, num_classes=1000):
        super().__init__()
        self.inplanes = 64
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(512 * block.expansion, num_classes)

    def _make_layer(self, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion, kernel_size=1,
                          stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion),
            )
        layers = [block(self.inplanes, planes, stride, downsample)]
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes))
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.maxpool(self.relu(self.bn1(self.conv1(x))))
        x = self.layer4(self.layer3(self.layer2(self.layer1(x))))
        b, c, h, w = x.shape
        # Spatial positions become a token sequence for the per-AU heads.
        return x.view(b, c, -1).permute(0, 2, 1)


def resnet50():
    return ResNet(Bottleneck, [3, 4, 6, 3])


# ---------------------------------------------------------------------------
# graph.py
# ---------------------------------------------------------------------------

def create_e_matrix(n):
    end = torch.zeros((n * n, n))
    for i in range(n):
        end[i * n:(i + 1) * n, i] = 1
    start = torch.zeros(n, n)
    for i in range(n):
        start[i, i] = 1
    start = start.repeat(n, 1)
    return start, end


# ---------------------------------------------------------------------------
# graph_edge_model.py
# ---------------------------------------------------------------------------

class CrossAttn(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.in_channels = in_channels
        self.linear_q = nn.Linear(in_channels, in_channels // 2)
        self.linear_k = nn.Linear(in_channels, in_channels // 2)
        self.linear_v = nn.Linear(in_channels, in_channels)
        self.scale = (self.in_channels // 2) ** -0.5
        self.attend = nn.Softmax(dim=-1)

    def forward(self, y, x):
        query = self.linear_q(y)
        key = self.linear_k(x)
        value = self.linear_v(x)
        dots = torch.matmul(query, key.transpose(-2, -1)) * self.scale
        return torch.matmul(self.attend(dots), value)


class GEM(nn.Module):
    def __init__(self, in_channels, num_classes):
        super().__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.FAM = CrossAttn(self.in_channels)
        self.ARM = CrossAttn(self.in_channels)
        self.edge_proj = nn.Linear(in_channels, in_channels)
        self.bn = nn.BatchNorm2d(self.num_classes * self.num_classes)

    def forward(self, class_feature, global_feature):
        B, N, D, C = class_feature.shape
        global_feature = global_feature.repeat(1, N, 1).view(B, N, D, C)
        feat = self.FAM(class_feature, global_feature)
        feat_end = feat.repeat(1, 1, N, 1).view(B, -1, D, C)
        feat_start = feat.repeat(1, N, 1, 1).view(B, -1, D, C)
        feat = self.ARM(feat_start, feat_end)
        return self.bn(self.edge_proj(feat))


# ---------------------------------------------------------------------------
# MEFL.py (stage 2)
# ---------------------------------------------------------------------------

class GNNLayer(nn.Module):
    def __init__(self, in_channels, num_classes, dropout_rate=0.1):
        super().__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        dim = self.in_channels
        self.U = nn.Linear(dim, dim, bias=False)
        self.V = nn.Linear(dim, dim, bias=False)
        self.A = nn.Linear(dim, dim, bias=False)
        self.B = nn.Linear(dim, dim, bias=False)
        self.E = nn.Linear(dim, dim, bias=False)
        self.dropout = nn.Dropout(dropout_rate)
        self.sigmoid = nn.Sigmoid()
        self.softmax = nn.Softmax(2)
        self.bnv = nn.BatchNorm1d(num_classes)
        self.bne = nn.BatchNorm1d(num_classes * num_classes)
        self.act = nn.ReLU()

    def forward(self, x, edge, start, end):
        res = x
        Vix = self.A(x)
        Vjx = self.B(x)
        e = self.E(edge)
        edge = edge + self.act(self.bne(
            torch.einsum('ev, bvc -> bec', (end, Vix))
            + torch.einsum('ev, bvc -> bec', (start, Vjx)) + e))

        e = self.sigmoid(edge)
        b, _, c = e.shape
        e = e.view(b, self.num_classes, self.num_classes, c)
        e = self.softmax(e)
        e = e.view(b, -1, c)

        Ujx = self.V(x)
        Ujx = torch.einsum('ev, bvc -> bec', (start, Ujx))
        Uix = self.U(x)
        x = Uix + torch.einsum('ve, bec -> bvc', (end.t(), e * Ujx)) / self.num_classes
        x = res + self.act(self.bnv(x))
        return x, edge


class GNN(nn.Module):
    def __init__(self, in_channels, num_classes, layer_num=2):
        super().__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        start, end = create_e_matrix(self.num_classes)
        self.register_buffer("start", start, persistent=False)
        self.register_buffer("end", end, persistent=False)
        self.graph_layers = nn.ModuleList(
            [GNNLayer(self.in_channels, self.num_classes) for _ in range(layer_num)])

    def forward(self, x, edge):
        for layer in self.graph_layers:
            x, edge = layer(x, edge, self.start, self.end)
        return x, edge


class Head(nn.Module):
    def __init__(self, in_channels, num_main_classes=27, num_sub_classes=14):
        super().__init__()
        self.in_channels = in_channels
        self.num_main_classes = num_main_classes
        self.num_sub_classes = num_sub_classes
        self.main_class_linears = nn.ModuleList(
            [LinearBlock(self.in_channels, self.in_channels) for _ in range(num_main_classes)])
        self.edge_extractor = GEM(self.in_channels, num_main_classes)
        self.gnn = GNN(self.in_channels, num_main_classes, 2)
        self.main_sc = nn.Parameter(torch.zeros(num_main_classes, self.in_channels))
        self.sub_sc = nn.Parameter(torch.zeros(num_sub_classes, self.in_channels))
        #: Indices into MAIN_AUS of the AUs that have a lateralised pair:
        #: AU 1, 2, 4, 6, 10, 12, 14.
        self.sub_list = [0, 1, 2, 4, 7, 8, 11]
        self.relu = nn.ReLU()

    def forward(self, x):
        f_u = torch.cat([layer(x).unsqueeze(1) for layer in self.main_class_linears], dim=1)
        f_v = f_u.mean(dim=-2)
        f_e = self.edge_extractor(f_u, x).mean(dim=-2)
        f_v, f_e = self.gnn(f_v, f_e)

        b, n, c = f_v.shape
        main_sc = F.normalize(self.relu(self.main_sc), p=2, dim=-1)
        main_cl = F.normalize(f_v, p=2, dim=-1)
        # Cosine similarity between two non-negative vectors, so each score is
        # in [0, 1]. Upstream thresholds it at 0.5 as an occurrence decision;
        # it is NOT an intensity and nothing in training calibrated it as a
        # probability either.
        main_cl = (main_cl * main_sc.view(1, n, c)).sum(dim=-1)

        sub_cl = []
        for i, index in enumerate(self.sub_list):
            main_au = F.normalize(f_v[:, index], p=2, dim=-1)
            sc_l = F.normalize(self.relu(self.sub_sc[2 * i]), p=2, dim=-1)
            sc_r = F.normalize(self.relu(self.sub_sc[2 * i + 1]), p=2, dim=-1)
            sub_cl.append((main_au * sc_l.view(1, c)).sum(dim=-1)[:, None])
            sub_cl.append((main_au * sc_r.view(1, c)).sum(dim=-1)[:, None])
        return torch.cat([main_cl, torch.cat(sub_cl, dim=-1)], dim=-1)


class MEFARG(nn.Module):
    def __init__(self, num_main_classes=27, num_sub_classes=14):
        super().__init__()
        self.backbone = resnet50()
        self.in_channels = self.backbone.fc.weight.shape[1]
        self.out_channels = self.in_channels // 4
        self.backbone.fc = None
        self.global_linear = LinearBlock(self.in_channels, self.out_channels)
        self.head = Head(self.out_channels, num_main_classes, num_sub_classes)

    def forward(self, x):
        return self.head(self.global_linear(self.backbone(x)))


def load_checkpoint(path) -> MEFARG:
    """Build the network and load the released weights, STRICTLY.

    Upstream loads with `strict=False`, and its demo builds the stage-1
    architecture whichever stage is requested. Measured here: the stage-2
    checkpoint loaded that way leaves 8 tensors at random initialisation and
    discards 49 — and runs, and emits plausible-looking numbers. A partial load
    is not a degraded model, it is a different one, so this raises instead.

    `weights_only=True` because a checkpoint is data from the internet and an
    unrestricted torch.load would execute whatever pickle it contains.
    """
    ckpt = torch.load(path, map_location="cpu", weights_only=True)
    state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
    state = {k[7:] if k.startswith("module.") else k: v for k, v in state.items()}
    net = MEFARG()
    net.load_state_dict(state, strict=True)
    return net.eval()


__all__ = ["MAIN_AUS", "LATERAL_AUS", "MEFARG", "load_checkpoint"]
