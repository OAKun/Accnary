# Accnary

Accnary is a Windows desktop manager for local account and password records. It uses a standard KDBX vault and runs on demand: open the application, search for an account, copy the needed field, then close it.

Accnary is licensed under [GPL-3.0-only](LICENSE). Third-party components retain their own licenses; the exact dependency versions are pinned in [`frame/requirements-lock.txt`](frame/requirements-lock.txt).

The application source, tests, build files, and project documentation are in [`frame/`](frame/). Local release artifacts and vault data are intentionally excluded from this repository.

## Project files

- [User guide](frame/docs/USER_GUIDE.md)
- [Threat model and remaining risks](frame/docs/THREAT_MODEL.md)
- [Data format](frame/docs/DATA_FORMAT.md)
- [Locked dependencies](frame/requirements-lock.txt)
- [License](LICENSE)

## Development

Use Python 3.14 on Windows. From `frame/`, install the pinned dependencies and run the test suite:

```powershell
pip install --require-hashes -r requirements-lock.txt
python -B -m pytest tests -p no:cacheprovider
```

The documented Windows packaging workflow is [`frame/build_exe.bat`](frame/build_exe.bat). It checks for a running Accnary instance and does not terminate it.

## Downloads

Windows builds are distributed through [ToolHub on CNB](https://cnb.cool/oakun/ToolHub).
