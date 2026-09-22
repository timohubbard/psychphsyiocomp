# Smart App Control is blocking Python wheels

## What is happening

```
ImportError: DLL load failed while importing dtypes:
An Application Control policy has blocked this file.
```

Confirmed on this machine:

```powershell
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' |
  Select VerifiedAndReputablePolicyState
# VerifiedAndReputablePolicyState : 1   (0 = off, 1 = enforcing, 2 = evaluation)
```

**Smart App Control is on and enforcing.** SAC blocks binaries that are neither
signed by a trusted publisher nor established in Microsoft's reputation data.
A Python wheel published last week is exactly that: an unsigned `.pyd`, with no
reputation yet.

This is not a Python problem and not a project problem. It will recur every time
a dependency publishes a new release, and it fails at *import*, not at install —
so `pip` reports success and the failure surfaces later, somewhere unrelated.

Observed so far:

| package | blocked | permitted |
|---|---|---|
| pandas | 3.0.6 | 2.3.3 |
| scikit-learn | 1.9.1 | 1.7.2 |

Both are pinned in `requirements.txt` with a comment saying the bound is a
policy constraint, not a correctness one.

## The one-way door

SAC can be turned off. **It cannot be turned back on without reinstalling
Windows** — that is documented Microsoft behaviour, not a quirk of this machine.
So "just disable it" trades a permanent, machine-wide security reduction for a
dependency convenience, and it should not be the first answer.

## Recommendation: run the Python side in WSL2

The architecture already points this way. The split is:

- **Browser / Windows** — the capture page, `getUserMedia`, the researcher app
  in Chrome. None of this touches the blocked wheels.
- **Python / server** — every engine, the pipeline, the canonical tables. All of
  the blocked wheels, none of the hardware access.

The Python half is pure batch processing over stored files. It has no reason to
run on Windows at all, and a real deployment would run it on Linux. Moving it to
WSL2 costs nothing architecturally and removes the whole class of problem: no
SAC, current wheels, and the same environment CI would use.

Virtualisation is already enabled on this machine (`HypervisorPresent: True`),
so this is one command plus a reboot:

```powershell
wsl --install           # needs admin; reboot afterwards
```

Then, inside WSL:

```bash
sudo apt install python3-venv ffmpeg
cd /mnt/c/Users/timhu/Desktop/myimotions
python3 -m venv .venv-linux
.venv-linux/bin/pip install -r requirements.txt
```

Working across `/mnt/c` is slower than a native Linux path. If that bites,
clone into the WSL filesystem (`~/myimotions`) and treat the Windows copy as the
one you edit in, or move development there entirely.

`ffmpeg` is worth installing at the same time: py-feat's video path needs
torchcodec + FFmpeg shared libraries, which is why the AU engine currently
decodes with OpenCV instead.

### What this also fixes

- The `pandas<3` and `scikit-learn<1.8` pins can be dropped.
- py-feat's native video decoding becomes available.
- Any future dependency with a fresh release stops being a coin flip.

## Alternatives, and why they are worse

**Keep pinning older versions.** What the repo does today. It works, but it is
whack-a-mole: each new blocked package needs diagnosing from an ImportError that
names a DLL rather than a policy, and the pins accumulate without a principled
reason anyone will remember.

**Turn SAC off.** Effective and irreversible. A permanent machine-wide security
reduction is a large price for a dependency convenience, and it is not needed —
the work that requires those wheels does not need to run on Windows.

**conda-forge instead of PyPI.** Might help, since conda-forge binaries are
built differently, but reputation is per-file and there is no guarantee any
given build is trusted. It trades a known problem for an unpredictable one.

**Add a WDAC exception for the venv.** Possible in principle, but SAC is not
user-configurable in the way an enterprise WDAC policy is, and hand-authoring CI
policy to whitelist a directory of unsigned binaries reproduces the security
downgrade with extra steps.

## If you keep working on Windows

Nothing is broken today — the full suite passes and both gates are green. When a
new `ImportError: ... Application Control policy has blocked this file` appears:

1. Note the package from the traceback.
2. `pip install "<package>=<older major/minor>"` and retry the import.
3. Pin it in `requirements.txt` **with a comment saying it is a policy bound**,
   so whoever reads it on Linux knows they can ignore it.

The top-level package importing successfully does not mean it works: SAC blocks
individual `.pyd` files, so `import sklearn` can succeed while
`sklearn.metrics._dist_metrics` fails. Test the import path the code actually
uses.
