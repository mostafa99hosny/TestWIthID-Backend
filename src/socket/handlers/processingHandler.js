const pythonWorker = require("../../scripts/core/pythonWorker/index")

module.exports = (socket, socketService) => {
    socket.on('start_taqeem_processing', async (data) => {
        const { batchId, reportIds, numTabs = 1, actionType = 'process' } = data;

        try {
            // Validate required fields
            if (!batchId) {
                throw new Error('batchId is required');
            }

            // Validate numTabs
            let validatedNumTabs = parseInt(numTabs);
            if (isNaN(validatedNumTabs) || validatedNumTabs < 1) {
                validatedNumTabs = 1;
            } else if (validatedNumTabs > 10) {
                validatedNumTabs = 10;
            }

            // Don't use more tabs than reports
            if (validatedNumTabs > reportIds.length) {
                validatedNumTabs = reportIds.length;
            }

            console.log(`[PROCESSING STARTED] Batch ${batchId} with ${reportIds.length} reports using ${validatedNumTabs} tabs`);

            // Join the batch room
            socket.join(`batch_${batchId}`);

            // Store session
            socketService.activeSessions.set(batchId, {
                socket,
                batchId,
                reportIds,
                numTabs: validatedNumTabs,
                startedAt: new Date(),
                userId: socket.userId
            });

            // Emit start confirmation
            socket.emit('processing_started', {
                batchId,
                status: 'STARTED',
                totalReports: reportIds.length,
                numTabs: validatedNumTabs,
                timestamp: new Date().toISOString()
            });

            // Emit to batch room
            socketService.io.to(`batch_${batchId}`).emit('batch_status_update', {
                batchId,
                status: 'PROCESSING_STARTED',
                totalReports: reportIds.length,
                numTabs: validatedNumTabs,
                timestamp: new Date().toISOString()
            });

            console.log(`[PYTHON WORKER] Sending batch ${batchId} to Python worker with ${validatedNumTabs} tabs`);

            // Start Python worker processing with multi-tab support
            const response = await pythonWorker.processTaqeemBatch(
                batchId,
                reportIds,
                validatedNumTabs,
                true
            );

            if (response.status === 'ACKNOWLEDGED') {
                console.log(`[PROCESSING ACKNOWLEDGED] Batch ${batchId} started with ${validatedNumTabs} tabs`);
            } else if (response.status === 'FAILED') {
                throw new Error(response.error || 'Failed to start processing');
            }

        } catch (error) {
            console.error(`[SOCKET ERROR] start_taqeem_processing:`, error);
            socket.emit('processing_error', {
                batchId,
                status: 'FAILED',
                error: error.message,
                timestamp: new Date().toISOString()
            });
            socketService.activeSessions.delete(batchId);
        }
    });

    socket.on('pause_processing', async (data) => {
        const { batchId } = data;

        try {
            console.log(`[PAUSE REQUEST] Batch ${batchId}`);
            const response = await pythonWorker.pauseProcessing(batchId);

            if (response.status === 'PAUSED') {
                socketService.io.to(`batch_${batchId}`).emit('processing_paused', {
                    batchId,
                    status: 'PAUSED',
                    timestamp: new Date().toISOString()
                });
                console.log(`[PROCESSING PAUSED] Batch ${batchId}`);
            } else if (response.status === 'FAILED') {
                throw new Error(response.error || 'Failed to pause processing');
            }
        } catch (error) {
            console.error(`[SOCKET ERROR] pause_processing:`, error);
            socket.emit('processing_error', {
                batchId,
                status: 'FAILED',
                error: error.message,
                timestamp: new Date().toISOString()
            });
        }
    });

    socket.on('resume_processing', async (data) => {
        const { batchId } = data;

        try {
            console.log(`[RESUME REQUEST] Batch ${batchId}`);
            const response = await pythonWorker.resumeProcessing(batchId);

            if (response.status === 'RESUMED') {
                socketService.io.to(`batch_${batchId}`).emit('processing_resumed', {
                    batchId,
                    status: 'RESUMED',
                    timestamp: new Date().toISOString()
                });
                console.log(`[PROCESSING RESUMED] Batch ${batchId}`);
            } else if (response.status === 'FAILED') {
                throw new Error(response.error || 'Failed to resume processing');
            }
        } catch (error) {
            console.error(`[SOCKET ERROR] resume_processing:`, error);
            socket.emit('processing_error', {
                batchId,
                status: 'FAILED',
                error: error.message,
                timestamp: new Date().toISOString()
            });
        }
    });

    socket.on('stop_processing', async (data) => {
        const { batchId } = data;

        try {
            console.log(`[STOP REQUEST] Batch ${batchId}`);
            const response = await pythonWorker.stopProcessing(batchId);

            if (response.status === 'STOPPED') {
                socketService.io.to(`batch_${batchId}`).emit('processing_stopped', {
                    batchId,
                    status: 'STOPPED',
                    timestamp: new Date().toISOString()
                });

                // Clean up session
                socketService.activeSessions.delete(batchId);
                console.log(`[PROCESSING STOPPED] Batch ${batchId}`);
            } else if (response.status === 'FAILED') {
                throw new Error(response.error || 'Failed to stop processing');
            }
        } catch (error) {
            console.error(`[SOCKET ERROR] stop_processing:`, error);
            socket.emit('processing_error', {
                batchId,
                status: 'FAILED',
                error: error.message,
                timestamp: new Date().toISOString()
            });
        }
    });

    // New event to update tab count for running batch (optional)
    socket.on('update_tab_count', async (data) => {
        const { batchId, numTabs } = data;

        try {
            socket.emit('error', {
                message: 'Cannot update tab count for running batch. Please stop and restart with new tab count.',
                batchId
            });
        } catch (error) {
            console.error(`[SOCKET ERROR] update_tab_count:`, error);
        }
    });
};