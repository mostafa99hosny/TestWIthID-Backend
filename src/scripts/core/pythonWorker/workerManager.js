const { spawn } = require('child_process');
const { getPythonPaths } = require('./config/paths');

class WorkerManager {
    constructor() {
        this.worker = null;
        this.stdoutBuffer = '';
    }

    startWorker() {
        if (this.worker && !this.worker.killed) {
            console.log('[PY] Worker already running');
            return this.worker;
        }

        const { pythonExecutable, scriptPath, scriptDir } = getPythonPaths();
        console.log(`[PY] Starting worker: ${pythonExecutable} ${scriptPath}`);

        this.worker = spawn(pythonExecutable, [scriptPath], {
            cwd: scriptDir,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        this.stdoutBuffer = '';

        this.worker.on('spawn', () => {
            console.log('[PY] Worker process spawned');
        });

        this.worker.on('close', (code, signal) => {
            console.log(`[PY] Worker exited (code=${code}, signal=${signal})`);
            this.worker = null;
        });

        this.worker.on('error', (error) => {
            console.error('[PY] Worker error:', error);
        });

        return this.worker;
    }

    setupStdoutHandler(handleOutputLine) {
        if (!this.worker) return;

        this.worker.stdout.on('data', (data) => {
            this.stdoutBuffer += data.toString();
            const lines = this.stdoutBuffer.split(/\r?\n/);
            this.stdoutBuffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;
                handleOutputLine(line);
            }
        });
    }

    setupStderrHandler() {
        if (!this.worker) return;

        this.worker.stderr.on('data', (data) => {
            console.log(`[PY STDERR] ${data.toString().trim()}`);
        });
    }

    sendToStdin(data) {
        if (this.worker && !this.worker.killed) {
            this.worker.stdin.write(data + '\n');
            return true;
        }
        return false;
    }

    killWorker(signal = 'SIGTERM') {
        if (this.worker) {
            this.worker.kill(signal);
            this.worker = null;
        }
    }

    isWorkerAlive() {
        return !!(this.worker && !this.worker.killed);
    }
}

module.exports = WorkerManager;