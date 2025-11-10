require('dotenv').config();
const express = require('express');
const cors = require('cors');
const connectDB = require("./infra/db/connection");
const mongoose = require('mongoose');
const corsOptions = require('./shared/config/cors.options');

// Import routes
const authRoutes = require('./presentation/routes/taqeemAuth.routes');
const taqeemSubmissionRoutes = require('./presentation/routes/taqeemSubmission.routes');
const taqeemDeleteRoutes = require('./presentation/routes/taqeemDelete.routes');
const testReportRoutes = require('./presentation/routes/testReport.routes');

const app = express();

app.use(cors(corsOptions));

connectDB();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
    next();
});

// Routes
app.use('/api/taqeemAuth', authRoutes);
app.use('/api/taqeemSubmission', taqeemSubmissionRoutes);
app.use('/api/taqeemDelete', taqeemDeleteRoutes);
app.use('/api/reports', testReportRoutes);


// Health check endpoint
app.get('/health', (req, res) => {
    res.status(200).json({
        status: 'OK',
        message: 'Server is running',
        database: mongoose.connection.readyState === 1 ? 'Connected' : 'Disconnected',
        timestamp: new Date().toISOString()
    });
});

// 404 handler for undefined routes

// Global error handling middleware
app.use((error, req, res, next) => {
    console.error('Error:', error);
    res.status(error.status || 500).json({
        success: false,
        message: error.message || 'Internal Server Error',
        ...(process.env.NODE_ENV === 'development' && { stack: error.stack })
    });
});

module.exports = app;