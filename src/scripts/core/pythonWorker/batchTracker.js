class BatchTracker {
    constructor() {
        this.completedBatches = new Set();
        this.activeSessions = new Map(); // Could track more batch metadata
    }

    markBatchCompleted(batchId) {
        this.completedBatches.add(batchId);
    }

    isBatchCompleted(batchId) {
        return this.completedBatches.has(batchId);
    }

    removeBatch(batchId) {
        this.completedBatches.delete(batchId);
    }

    clearAll() {
        this.completedBatches.clear();
    }

    getCompletedCount() {
        return this.completedBatches.size;
    }
}

module.exports = BatchTracker;