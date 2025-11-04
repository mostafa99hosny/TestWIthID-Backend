module.exports = (socket, socketService) => {
    socket.on('disconnect', async (reason) => {
        console.log(`User ${socket.id} (user: ${socket.userId}) disconnected. Reason: ${reason} at ${new Date().toISOString()}`);

        const isIntentionalDisconnect = reason === 'io client disconnect' || reason === 'io server disconnect';

        // Immediate cleanup only for intentional disconnects
        if (isIntentionalDisconnect) {
            console.log(`[IMMEDIATE CLEANUP] Intentional disconnect for ${socket.id}`);
            if (socket.userId) {
                await socketService.performCleanupByUserId(socket.userId);
            }
            return;
        }

        // For temporary disconnections, use delayed cleanup
        if (socket.userId) {
            console.log(`[DELAYED CLEANUP] User ${socket.userId} disconnected (${reason}). Waiting 25 seconds...`);

            const timeoutId = setTimeout(async () => {
                console.log(`[CLEANUP] No reconnection for user ${socket.userId}, performing cleanup`);
                await socketService.performCleanupByUserId(socket.userId);
            }, 25000);

            socketService.userSessions.set(socket.userId, {
                cleanupTimeout: timeoutId,
                disconnectedAt: new Date(),
                lastSocketId: socket.id
            });
        }
    });

    socket.on('error', (error) => {
        console.error(`[SOCKET ERROR] Socket ${socket.id} error:`, error);
    });
};