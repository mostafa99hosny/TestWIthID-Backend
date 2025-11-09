const { spawn } = require('child_process');
const path = require('path');

class PythonWorker {
    constructor() {
        this.worker = null;
        this.stdoutBuffer = '';
        this.pendingCommands = new Map();
        this.commandId = 0;
        this.isWorkerReady = false;
        this.completedBatches = new Set();
    }

    startWorker() {
        if (this.worker && !this.worker.killed) {
            console.log('[PY] Worker already running');
            return this.worker;
        }

        const isWindows = process.platform === 'win32';
        const pythonExecutable = isWindows
            ? path.join(__dirname, '../../../../.venv/Scripts/python.exe')
            : path.join(__dirname, '../../../../.venv/bin/python');

        const repoRoot = path.resolve(__dirname, '../../../..');
        const srcDir = path.join(repoRoot, 'src');
        const modulePath = 'scripts.core.browser.worker_taqeem';

        console.log(`[PY] Starting worker (module): ${pythonExecutable} -m ${modulePath}`);
        this.worker = spawn(pythonExecutable, ['-m', modulePath], {
            cwd: srcDir,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: {
                ...process.env,
                PYTHONPATH: srcDir
            }
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
            this.completedBatches.clear();

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

            // Handle progress updates with enhanced macro edit support
            if (response.type === 'PROGRESS') {
                const io = require('../../../socket/socketService').getIO();
                if (io && response.reportId) {
                    const progressData = {
                        reportId: response.reportId,
                        status: response.status,
                        message: response.message,
                        data: {
                            percentage: response.percentage || 0,
                            current: response.current,
                            total: response.total,
                            macro_id: response.macro_id,
                            failed_records: response.failed_records,
                            numTabs: response.numTabs,
                            error: response.error
                        },
                        timestamp: new Date().toISOString()
                    };

                    // Emit to report-specific room
                    io.to(`progress_${response.reportId}`).emit('macro_edit_progress', progressData);

                    // Also emit to batch room if batchId exists
                    if (response.batchId) {
                        io.to(`batch_${response.batchId}`).emit('processing_progress', response);
                    }

                    // Handle completion - prevent duplicate emits
                    if (response.status === 'COMPLETED' && !this.completedBatches.has(response.reportId)) {
                        this.completedBatches.add(response.reportId);

                        const completionData = {
                            reportId: response.reportId,
                            batchId: response.batchId,
                            status: 'COMPLETED',
                            message: response.message,
                            data: {
                                percentage: 100,
                                failedRecords: response.failed_records || 0,
                                numTabs: response.numTabs || 1,
                                total: response.total,
                                current: response.current
                            },
                            timestamp: new Date().toISOString()
                        };

                        io.to(`progress_${response.reportId}`).emit('macro_edit_complete', completionData);

                        if (response.batchId) {
                            io.to(`batch_${response.batchId}`).emit('processing_complete', completionData);
                            const socketService = require('../../../socket/socketService');
                            socketService.activeSessions.delete(response.batchId);
                        }

                        console.log(`[MACRO EDIT COMPLETE] Report ${response.reportId} completed using ${response.numTabs || 1} tabs`);

                        // Clear completion tracking after a delay
                        setTimeout(() => {
                            this.completedBatches.delete(response.reportId);
                        }, 5000);
                    }

                    // Handle errors
                    if (response.status === 'FAILED' || response.status === 'ERROR') {
                        const errorData = {
                            reportId: response.reportId,
                            batchId: response.batchId,
                            status: 'FAILED',
                            error: response.error || response.message,
                            data: {
                                macro_id: response.macro_id
                            },
                            timestamp: new Date().toISOString()
                        };

                        io.to(`progress_${response.reportId}`).emit('macro_edit_error', errorData);

                        if (response.batchId) {
                            io.to(`batch_${response.batchId}`).emit('processing_error', errorData);
                        }
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
                        const io = require('../../../socket/socketService').getIO();
                        const socketService = require('../../../socket/socketService');

                        if (response.status === 'STOPPED') {
                            io.to(`batch_${response.batchId}`).emit('processing_stopped', {
                                batchId: response.batchId,
                                status: 'STOPPED',
                                message: response.message,
                                timestamp: new Date().toISOString()
                            });
                            socketService.activeSessions.delete(response.batchId);
                            this.completedBatches.delete(response.batchId);
                            console.log(`[PROCESSING STOPPED] Batch ${response.batchId}`);
                        } else if (response.status === 'FAILED') {
                            io.to(`batch_${response.batchId}`).emit('processing_error', {
                                batchId: response.batchId,
                                status: 'FAILED',
                                error: response.error,
                                timestamp: new Date().toISOString()
                            });
                            socketService.activeSessions.delete(response.batchId);
                            this.completedBatches.delete(response.batchId);
                            console.log(`[PROCESSING FAILED] Batch ${response.batchId}`);
                        } else if (response.status === 'SUCCESS') {
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
            await new Promise((resolve, reject) => {
                const w = this.startWorker();
                const onSpawn = () => {
                    w.off('error', onError);
                    resolve();
                };
                const onError = (err) => {
                    w.off('spawn', onSpawn);
                    reject(err);
                };
                w.once('spawn', onSpawn);
                w.once('error', onError);
            });
        }

        const commandId = this.commandId++;
        const commandWithId = { ...command, commandId };

        return new Promise((resolve, reject) => {
            this.pendingCommands.set(commandId, { resolve, reject });

            try {
                this.worker.stdin.write(JSON.stringify(commandWithId) + '\n');
                console.log(
                    `[PY] Sent command: ${command.action} (id: ${commandId})`,
                    command.tabsNum ? `with ${command.tabsNum} tabs` : ''
                );
            } catch (error) {
                this.pendingCommands.delete(commandId);
                reject(new Error(`Failed to send command to worker: ${error.message}`));
            }
        });
    }

    async ping() {
        return this.sendCommand({ action: 'ping' });
    }

    async login(email, password, method = null) {
        return this.sendCommand({
            action: 'login',
            email,
            password,
            method
        });
    }

    async submitOtp(otp, recordId = null) {
        return this.sendCommand({
            action: 'otp',
            otp,
            recordId
        });
    }

    async validateExcelData(reportId) {
        return this.sendCommand({
            action: 'validate_excel_data',
            reportId,
        });
    }

    async deleteReport(reportId) {
        return this.sendCommand({
            action: 'delete_report',
            reportId,
            templatePath: './data/asset_template.json'
        });
    }

    async createAssets(reportId, macroCount, tabsNum = 3) {
        let validatedTabsNum = parseInt(tabsNum);
        if (isNaN(validatedTabsNum) || validatedTabsNum < 1) {
            validatedTabsNum = 1;
        } else if (validatedTabsNum > 10) {
            validatedTabsNum = 10;
        }

        let validatedMacroCount = parseInt(macroCount);
        if (isNaN(validatedMacroCount) || validatedMacroCount < 1) {
            throw new Error('Invalid macro count');
        }

        console.log(`[PY] Creating ${validatedMacroCount} assets for report ${reportId} using ${validatedTabsNum} tabs`);

        return this.sendCommand({
            action: 'create_assets',
            reportId,
            macroCount: validatedMacroCount,
            tabsNum: validatedTabsNum,
        });
    }

    async grabMacroIds(reportId, tabsNum) {
        return this.sendCommand({
            action: 'grab_ids',
            reportId,
            tabsNum
        });
    }

    async editMacros(reportId, tabsNum = 3) {
        let validatedTabsNum = parseInt(tabsNum);
        if (isNaN(validatedTabsNum) || validatedTabsNum < 1) {
            validatedTabsNum = 1;
        } else if (validatedTabsNum > 10) {
            validatedTabsNum = 10;
        }

        console.log(`[PY] Editing macros for report ${reportId} using ${validatedTabsNum} tabs`);

        return this.sendCommand({
            action: 'edit_macros',
            reportId,
            tabsNum: validatedTabsNum
        });
    }

    async checkMacroStatus(reportId, tabsNum = 3) {
        return this.sendCommand({
            action: 'check_macro_status',
            reportId,
            tabsNum
        });
    }

    async halfCheckMacroStatus(reportId, tabsNum = 3) {
        return this.sendCommand({
            action: 'half_check_macro_status',
            reportId,
            tabsNum
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
                this.completedBatches.clear();
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