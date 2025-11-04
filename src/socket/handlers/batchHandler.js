module.exports = (socket, socketService) => {
    socket.on('join_batch', (batchId) => {
        socket.join(`batch_${batchId}`);
        console.log(`User ${socket.id} joined batch ${batchId}`);
    });
};