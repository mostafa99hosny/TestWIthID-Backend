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

    socket.on('pause_processing', async (data) => {
        const { reportId } = data;
        console.log(`[SOCKET] Pause request for report: ${reportId}`);

        try {
            const pythonWorker = require('../scripts/core/pythonWorker/index');
            const result = await pythonWorker.pauseProcessing(reportId);

            socket.emit('pause_result', {
                success: result.status === 'PAUSED',
                reportId,
                data: result
            });
        } catch (error) {
            socket.emit('pause_result', {
                success: false,
                reportId,
                error: error.message
            });
        }
    });

    // Handle resume request from frontend (optional - can also go through HTTP)
    socket.on('resume_processing', async (data) => {
        const { reportId } = data;
        console.log(`[SOCKET] Resume request for report: ${reportId}`);

        try {
            const pythonWorker = require('../scripts/core/pythonWorker/index');
            const result = await pythonWorker.resumeProcessing(reportId);

            socket.emit('resume_result', {
                success: result.status === 'RESUMED',
                reportId,
                data: result
            });
        } catch (error) {
            socket.emit('resume_result', {
                success: false,
                reportId,
                error: error.message
            });
        }
    });
};