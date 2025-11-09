// Socket handler for progress room management
// Place this in: backend/src/socket/handlers/progressHandler.js

module.exports = (socket, socketService) => {
    // Join progress room for a specific report
    socket.on('join_progress_room', (reportId) => {
        if (!reportId) {
            console.error('[PROGRESS] Cannot join room: reportId is missing');
            return;
        }

        const roomName = `progress_${reportId}`;
        socket.join(roomName);
        console.log(`[PROGRESS] Socket ${socket.id} joined room ${roomName}`);

        // Send confirmation
        socket.emit('progress_room_joined', {
            reportId,
            timestamp: new Date().toISOString()
        });
    });

    // Leave progress room
    socket.on('leave_progress_room', (reportId) => {
        if (!reportId) {
            console.error('[PROGRESS] Cannot leave room: reportId is missing');
            return;
        }

        const roomName = `progress_${reportId}`;
        socket.leave(roomName);
        console.log(`[PROGRESS] Socket ${socket.id} left room ${roomName}`);

        // Send confirmation
        socket.emit('progress_room_left', {
            reportId,
            timestamp: new Date().toISOString()
        });
    });

    // Request current progress status for a report
    socket.on('get_progress_status', (reportId) => {
        if (!reportId) {
            socket.emit('progress_status_error', {
                error: 'reportId is required',
                timestamp: new Date().toISOString()
            });
            return;
        }

        // Check if there's an active session for this report
        let activeSession = null;
        for (const [sessionId, session] of socketService.activeSessions.entries()) {
            if (session.reportId === reportId) {
                activeSession = session;
                break;
            }
        }

        socket.emit('progress_status', {
            reportId,
            active: !!activeSession,
            session: activeSession || null,
            timestamp: new Date().toISOString()
        });
    });
};