const WorkerActions = {
    PING: 'ping',
    LOGIN: 'login',
    OTP: 'otp',
    PROCESS_BATCH: 'processTaqeemBatch',
    GET_COMPANIES: 'getCompanies',
    PAUSE: 'pause',
    RESUME: 'resume',
    STOP: 'stop',
    CLOSE: 'close'
};

const EventTypes = {
    PROGRESS: 'PROGRESS',
    COMPLETED: 'COMPLETED',
    STOPPED: 'STOPPED',
    FAILED: 'FAILED',
    SUCCESS: 'SUCCESS'
};

const SocketEvents = {
    PROCESSING_PROGRESS: 'processing_progress',
    PROCESSING_COMPLETE: 'processing_complete',
    PROCESSING_STOPPED: 'processing_stopped',
    PROCESSING_ERROR: 'processing_error'
};

const Config = {
    DEFAULT_TABS: 1,
    MIN_TABS: 1,
    MAX_TABS: 10,
    RESTART_DELAY: 1000
};

module.exports = {
    WorkerActions,
    EventTypes,
    SocketEvents,
    Config
};