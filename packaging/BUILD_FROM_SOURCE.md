# Build the standalone Windows package

Developer requirements: Node 24 or later, Python 3.12 or later, internet access to pinned public dependencies. End users require none of these tools.

From this source root:

```sh
npm ci
python packaging/prepare_runtime.py
python -m pip install -r requirements.txt
npm test
npm run test:quant
npm run typecheck
npm run build
npm run package:win
```

On Linux use python3. @electron/packager cross-builds Windows x64 and sets the executable icon and product metadata using resedit. The release folder contains QuantEngine.exe and all resources; distribute the entire folder as a ZIP.

The runtime preparation script verifies the official Python manifest SHA and pinned PyPI wheel SHAs. Windows receives an independent embedded Python 3.13.16 runtime with NumPy/SciPy cp313 win_amd64 libraries. The launcher explicitly uses UTF-8 mode and unbuffered pipes. Host numerical tests may run a different compatible Python interpreter; the Windows acceptance step remains necessary.

Native self-test: launch the platform's Electron runtime with this root and --self-test. It uses isolated temporary storage, runs a real numerical calculation and skips the single-instance lock only in this isolated mode. The Windows EXE also accepts --self-test from a test runner. Device checks are in docs/EVALUATION.md.
