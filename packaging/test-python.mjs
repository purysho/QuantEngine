// Runs the numerical suite with QUANT_PYTHON, else `python` on Windows and `python3` elsewhere.
import { spawnSync } from 'node:child_process';

const python = process.env.QUANT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
// -t . puts the project root on sys.path, which embedded (._pth) runtimes otherwise omit.
const result = spawnSync(python, ['-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-p', 'test_*.py', ...process.argv.slice(2)],
  { stdio: 'inherit', env: { ...process.env, PYTHONUTF8: '1' } });
if (result.error) { console.error(`Could not start ${python}: ${result.error.message}`); process.exit(1); }
process.exit(result.status ?? 1);
