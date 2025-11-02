const { spawn } = require('child_process');
const path = require('path');

class PythonWorker {
    constructor() {
        this.worker = null;
        this.stdoutBuffer = '';
        this.pendingCommands = new Map();
        this.commandId = 0;
        this.isWorkerReady = false;
        this.completedBatches = new Set(); // Track completed batches to prevent duplicate emits
    }

    startWorker() {
        if (this.worker && !this.worker.killed) {
            console.log('[PY] Worker already running');
            return this.worker;
        }

        const isWindows = process.platform === 'win32';
        const pythonExecutable = isWindows
            ? path.join(__dirname, '../../.venv/Scripts/python.exe')
            : path.join(__dirname, '../../../../.venv/bin/python');

        const scriptPath = path.join(__dirname, '../browser/worker_taqeem.py');
        const scriptDir = path.dirname(scriptPath);

        console.log(`[PY] Starting worker: ${pythonExecutable} ${scriptPath}`);

        this.worker = spawn(pythonExecutable, [scriptPath], {
            cwd: scriptDir,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        this.stdoutBuffer = '';
        this.isWorkerReady = false;

        this.worker.stdout.on('data', (data) => {
            this.stdoutBuffer += data.toString();
            const lines = this.stdoutBuffer.split(/\r?\n/);
            this.stdoutBuffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;
                this.handleWorkerOutput(line);
            }
        });

        this.worker.stderr.on('data', (data) => {
            console.log(`[PY STDERR] ${data.toString().trim()}`);
        });

        this.worker.on('spawn', () => {
            console.log('[PY] Worker process spawned');
            this.isWorkerReady = true;
        });

        this.worker.on('close', (code, signal) => {
            console.log(`[PY] Worker exited (code=${code}, signal=${signal})`);
            this.isWorkerReady = false;
            this.worker = null;
            this.completedBatches.clear(); // Clear completed batches on worker close

            this.pendingCommands.forEach((handler) => {
                handler.reject(new Error(`Worker exited with code ${code}`));
            });
            this.pendingCommands.clear();
        });

        this.worker.on('error', (error) => {
            console.error('[PY] Worker error:', error);
            this.isWorkerReady = false;
        });

        return this.worker;
    }

    handleWorkerOutput(line) {
        try {
            const response = JSON.parse(line);
            console.log('[PY] Response:', response);

            // Handle progress updates
            if (response.type === 'PROGRESS') {
                const io = require('./socketService').getIO();
                if (io && response.batchId) {
                    // Emit regular progress updates
                    io.to(`batch_${response.batchId}`).emit('processing_progress', response);
                    
                    // Only emit processing_complete ONCE per batch
                    if (response.status === 'COMPLETED' && !this.completedBatches.has(response.batchId)) {
                        this.completedBatches.add(response.batchId);
                        
                        io.to(`batch_${response.batchId}`).emit('processing_complete', {
                            batchId: response.batchId,
                            status: 'COMPLETED',
                            message: response.message,
                            failedRecords: response.failed_records || 0,
                            numTabs: response.numTabs,
                            percentage: 100,
                            timestamp: new Date().toISOString()
                        });
                        
                        const socketService = require('./socketService');
                        socketService.activeSessions.delete(response.batchId);
                        console.log(`[PROCESSING COMPLETE] Batch ${response.batchId} completed using ${response.numTabs || 1} tabs`);
                    }
                }
                return;
            }

            // Handle command responses
            if (response.commandId !== undefined) {
                const handler = this.pendingCommands.get(response.commandId);
                if (handler) {
                    handler.resolve(response);
                    this.pendingCommands.delete(response.commandId);
                    
                    if (response.batchId && (response.status === 'SUCCESS' || response.status === 'STOPPED' || response.status === 'FAILED')) {
                        const io = require('./socketService').getIO();
                        const socketService = require('./socketService');
                        
                        if (response.status === 'STOPPED') {
                            io.to(`batch_${response.batchId}`).emit('processing_stopped', {
                                batchId: response.batchId,
                                status: 'STOPPED',
                                message: response.message,
                                timestamp: new Date().toISOString()
                            });
                            socketService.activeSessions.delete(response.batchId);
                            this.completedBatches.delete(response.batchId); // Remove from completed batches
                            console.log(`[PROCESSING STOPPED] Batch ${response.batchId}`);
                        } else if (response.status === 'FAILED') {
                            io.to(`batch_${response.batchId}`).emit('processing_error', {
                                batchId: response.batchId,
                                status: 'FAILED',
                                error: response.error,
                                timestamp: new Date().toISOString()
                            });
                            socketService.activeSessions.delete(response.batchId);
                            this.completedBatches.delete(response.batchId); // Remove from completed batches
                            console.log(`[PROCESSING FAILED] Batch ${response.batchId}`);
                        } else if (response.status === 'SUCCESS') {
                            // Clean up completed batch from tracking
                            this.completedBatches.delete(response.batchId);
                        }
                    }
                }
            }

        } catch (error) {
            console.error('[PY] Failed to parse worker output:', line, error);
        }
    }

    async sendCommand(command) {
        if (!this.worker || !this.isWorkerReady) {
            this.startWorker();
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        const commandId = this.commandId++;
        const commandWithId = { ...command, commandId };

        return new Promise((resolve, reject) => {
            this.pendingCommands.set(commandId, {
                resolve: (result) => {
                    resolve(result);
                },
                reject: (error) => {
                    reject(error);
                }
            });

            try {
                this.worker.stdin.write(JSON.stringify(commandWithId) + '\n');
                console.log(`[PY] Sent command: ${command.action} (id: ${commandId})`, 
                    command.numTabs ? `with ${command.numTabs} tabs` : '');
            } catch (error) {
                this.pendingCommands.delete(commandId);
                reject(new Error(`Failed to send command to worker: ${error.message}`));
            }
        });
    }

    async ping() {
        return this.sendCommand({ action: 'ping' });
    }

    async login(email, password, recordId = null) {
        return this.sendCommand({
            action: 'login',
            email,
            password,
            recordId
        });
    }

    async submitOtp(otp, recordId = null) {
        return this.sendCommand({
            action: 'otp',
            otp,
            recordId
        });
    }

    async processTaqeemBatch(batchId, reportIds, numTabs = 1, socketMode = true) {
        // Validate and sanitize numTabs
        let validatedNumTabs = parseInt(numTabs);
        if (isNaN(validatedNumTabs) || validatedNumTabs < 1) {
            validatedNumTabs = 1;
        } else if (validatedNumTabs > 10) {
            validatedNumTabs = 10; // Max safety limit
        }

        console.log(`[PY] Processing batch ${batchId} with ${reportIds.length} reports using ${validatedNumTabs} tabs`);

        return this.sendCommand({
            action: 'processTaqeemBatch',
            batchId,
            reportIds,
            numTabs: validatedNumTabs,
            socketMode
        });
    }

    async pauseProcessing(batchId) {
        return this.sendCommand({
            action: 'pause',
            batchId
        });
    }

    async resumeProcessing(batchId) {
        return this.sendCommand({
            action: 'resume',
            batchId
        });
    }

    async stopProcessing(batchId) {
        return this.sendCommand({
            action: 'stop',
            batchId
        });
    }

    async closeBrowser() {
        return this.sendCommand({
            action: 'close'
        });
    }

    async closeWorker() {
        if (!this.worker) return;

        try {
            await this.sendCommand({ action: 'close' });
        } catch (error) {
            console.log('[PY] Close command failed, forcing shutdown:', error.message);
        } finally {
            if (this.worker) {
                this.worker.kill('SIGTERM');
                this.worker = null;
                this.isWorkerReady = false;
                this.completedBatches.clear(); // Clear tracking on shutdown
            }
        }
    }

    isReady() {
        return this.isWorkerReady && this.worker && !this.worker.killed;
    }

    getStatus() {
        return {
            ready: this.isReady(),
            workerRunning: !!this.worker,
            pendingCommands: this.pendingCommands.size
        };
    }
}

module.exports = PythonWorker;