const { Server } = require('socket.io');

class SocketService {
    constructor() {
        this.io = null;
        this.activeSessions = new Map();
        this.userSessions = new Map();
    }

    initialize(server) {
        this.io = new Server(server, {
            cors: {
                origin: process.env.FRONTEND_URL || "*",
                methods: ["GET", "POST"]
            },
            pingInterval: 20000,
            pingTimeout: 10000,
            maxHttpBufferSize: 1e6,
            transports: ['websocket', 'polling']
        });

        this.setupEventHandlers();
        return this.io;
    }

    setupEventHandlers() {
        this.io.on('connection', (socket) => {
            console.log('User connected:', socket.id, 'at', new Date().toISOString());

            // Import and use modular event handlers
            require('./handlers/userHandler')(socket, this);
            require('./handlers/batchHandler')(socket, this);
            require('./handlers/processingHandler')(socket, this);
            require('./handlers/sessionHandler')(socket, this);
            require('./handlers/disconnectHandler')(socket, this);
        });
    }

    // Cleanup methods
    async performCleanupByUserId(userId) {
        try {
            console.log(`[BROWSER CLEANUP] Closing browser for user: ${userId}`);

            const sessionsToDelete = [];
            for (const [sessionId, session] of this.activeSessions.entries()) {
                if (session.userId === userId) {
                    sessionsToDelete.push(sessionId);
                }
            }

            sessionsToDelete.forEach(sessionId => {
                this.activeSessions.delete(sessionId);
                console.log(`[SESSION CLEANUP] Removed session ${sessionId}`);
            });

            // TODO: Add Python worker cleanup when we implement it
            // await sendCommand({ action: "close", userId });

            this.userSessions.delete(userId);
            console.log(`[CLEANUP COMPLETE] User ${userId} fully cleaned up`);
        } catch (error) {
            console.error(`[CLEANUP ERROR] Failed to cleanup for user ${userId}:`, error);
            this.userSessions.delete(userId);
        }
    }

    cancelUserCleanup(userId) {
        const userSession = this.userSessions.get(userId);
        if (userSession && userSession.cleanupTimeout) {
            clearTimeout(userSession.cleanupTimeout);
            this.userSessions.delete(userId);
            console.log(`[CLEANUP CANCELLED] User ${userId} reconnected successfully`);
            return true;
        }
        return false;
    }

    // Getter for io instance
    getIO() {
        return this.io;
    }
}

module.exports = new SocketService()
