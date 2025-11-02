const { SocketEvents, EventTypes } = require('./config/constants');

class SocketEmitter {
    constructor() {
        this.socketService = null;
    }

    setSocketService(socketService) {
        this.socketService = socketService;
    }

    emitToBatch(batchId, event, data) {
        if (!this.socketService) {
            console.warn(`[SOCKET] No socket service available for event: ${event}`);
            return;
        }

        const io = this.socketService.getIO();
        if (io) {
            io.to(`batch_${batchId}`).emit(event, data);
        }
    }

    emitProgress(batchId, progressData) {
        this.emitToBatch(batchId, SocketEvents.PROCESSING_PROGRESS, progressData);
    }

    emitComplete(batchId, completeData) {
        this.emitToBatch(batchId, SocketEvents.PROCESSING_COMPLETE, {
            batchId,
            status: 'COMPLETED',
            message: completeData.message,
            failedRecords: completeData.failed_records || 0,
            numTabs: completeData.numTabs,
            percentage: 100,
            timestamp: new Date().toISOString()
        });
    }

    emitStopped(batchId, message) {
        this.emitToBatch(batchId, SocketEvents.PROCESSING_STOPPED, {
            batchId,
            status: 'STOPPED',
            message,
            timestamp: new Date().toISOString()
        });
    }

    emitError(batchId, error) {
        this.emitToBatch(batchId, SocketEvents.PROCESSING_ERROR, {
            batchId,
            status: 'FAILED',
            error,
            timestamp: new Date().toISOString()
        });
    }

    cleanupSession(batchId) {
        if (this.socketService && this.socketService.activeSessions) {
            this.socketService.activeSessions.delete(batchId);
        }
    }
}

module.exports = SocketEmitter;