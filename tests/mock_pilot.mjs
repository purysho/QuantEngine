// Fault injection consumer; intentionally omits durable processing. Never production.
import readline from 'node:readline';
const mode = process.env.QUANT_TEST_PILOT_MODE;
const rl = readline.createInterface({input:process.stdin});
rl.on('line', () => {
  if (mode === 'duplicate') process.stdout.write('{"ack":1}\n{"ack":1}\n');
  else if (mode === 'invalid') process.stdout.write('not-json\n');
});
rl.on('close', () => {
  if (mode === 'hang') setInterval(() => {}, 1000);
});
