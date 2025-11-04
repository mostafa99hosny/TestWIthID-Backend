module.exports = (socket, socketService) => {
    socket.on('user_identified', (userId) => {
        if (!userId || typeof userId !== 'string') {
            console.warn(`[INVALID USER ID] Socket ${socket.id} provided invalid userId:`, userId);
            return;
        }

        socket.userId = userId;
        console.log(`Socket ${socket.id} identified as user ${userId}`);

        // Cancel pending cleanup for this user
        if (socketService.cancelUserCleanup(userId)) {
            console.log(`[REJOINED] User ${userId} rejoined existing sessions`);
        }
    });
};