import { spawn } from 'node:child_process';

const production = process.argv.includes('--production');
const port = process.env.FRONTEND_PORT ?? process.env.PORT ?? '3000';
const command = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const args = production ? ['next', 'start', '-p', port] : ['next', 'dev', '-p', port];

console.log(`Starting Next.js ${production ? 'production' : 'development'} server on port ${port}`);

const child = spawn(command, args, { stdio: 'inherit', env: { ...process.env, PORT: port } });

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 0);
});
