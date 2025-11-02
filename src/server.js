require('dotenv').config();
const app = require('./app');
const http = require('http');

const PORT = process.env.PORT || 5000;

// Create HTTP server
const server = http.createServer(app);

server.listen(PORT, () => {
  console.log(`
  🚀 Server running in ${process.env.NODE_ENV || 'development'} mode
  📍 Port: ${PORT}
  🔗 Health check: http://localhost:${PORT}/health
  ⏰ Started at: ${new Date().toISOString()}
  📡 Socket.IO server active
  `);
});

