module.exports = (socket, socketService) => {
    socket.on('get_active_sessions', () => {
        const sessions = Array.from(socketService.activeSessions.entries()).map(([batchId, session]) => ({
            batchId,
            startedAt: session.startedAt,
            totalReports: session.reportIds.length,
            userId: session.userId
        }));
        socket.emit('active_sessions', sessions);
    });
};