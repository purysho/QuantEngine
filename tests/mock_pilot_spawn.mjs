import child from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
const original = child.spawn;
child.spawn = (_command, _args, options) => original(process.execPath, ['tests/mock_pilot.mjs'], options);
syncBuiltinESMExports();
