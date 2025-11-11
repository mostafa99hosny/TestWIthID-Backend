const pythonWorker = require("../../scripts/core/pythonWorker/index");

const login = async (req, res) => {
    try {
        const { email, password, method } = req.body;

        if (!email || !password) {
            return res.status(400).json({
                success: false,
                error: 'Email and password are required'
            });
        }

        console.log(`[AUTH] Login attempt for: ${email}`);

        const result = await pythonWorker.login(email, password, method);

        if (result.status === 'OTP_REQUIRED') {
            return res.json({
                success: true,
                requiresOtp: true,
                message: 'OTP required to complete login',
                data: result
            });
        }

        if (result.status === 'LOGIN_SUCCESS') {
            return res.json({
                success: true,
                message: 'Login successful',
                data: result
            });
        }

        // Handle other statuses
        if (result.status === 'NOT_FOUND') {
            return res.status(401).json({
                success: false,
                error: 'Invalid credentials',
                recoverable: result.recoverable
            });
        }

        return res.status(400).json({
            success: false,
            error: result.error || 'Login failed',
            data: result
        });

    } catch (error) {
        console.error('[AUTH] Login error:', error);

        // Differentiate between timeout and other errors
        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
};

const submitOtp = async (req, res) => {
    try {
        const { otp, recordId } = req.body;

        if (!otp) {
            return res.status(400).json({
                success: false,
                error: 'OTP is required'
            });
        }

        console.log(`[AUTH] OTP submission attempt`);

        const result = await pythonWorker.submitOtp(otp, recordId);

        if (result.status === 'SUCCESS') {
            return res.json({
                success: true,
                message: 'OTP verified successfully',
                data: result
            });
        }

        if (result.status === 'OTP_FAILED') {
            return res.status(400).json({
                success: false,
                error: 'Invalid OTP',
                recoverable: result.recoverable,
                data: result
            });
        }

        return res.status(400).json({
            success: false,
            error: result.error || 'OTP verification failed',
            data: result
        });

    } catch (error) {
        console.error('[AUTH] OTP error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
};

const logout = async (req, res) => {
    try {
        const result = await pythonWorker.closeBrowser();

        res.json({
            success: true,
            message: 'Logged out successfully',
            data: result
        });

    } catch (error) {
        console.error('[AUTH] Logout error:', error);

        // Even if logout fails, consider it successful from client perspective
        // to avoid leaving them in a bad state
        res.json({
            success: true,
            message: 'Logout completed (with warnings)',
            warning: error.message
        });
    }
};

const getAuthStatus = async (req, res) => {
    try {
        const status = pythonWorker.getStatus();

        res.json({
            success: true,
            data: {
                worker: status,
                authenticated: status.ready
            }
        });

    } catch (error) {
        console.error('[AUTH] Status error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

// Health check endpoint for monitoring
const healthCheck = async (req, res) => {
    try {
        const isReady = pythonWorker.isReady();

        if (!isReady) {
            return res.status(503).json({
                success: false,
                error: 'Worker not ready'
            });
        }

        // Try a ping to verify worker is responsive
        const pingResult = await pythonWorker.ping();

        res.json({
            success: true,
            message: 'Worker healthy',
            data: pingResult
        });

    } catch (error) {
        console.error('[AUTH] Health check failed:', error);
        res.status(503).json({
            success: false,
            error: 'Worker unhealthy: ' + error.message
        });
    }
};

const checkBrowserStatus = async (req, res) => {
    try {
        console.log('[BROWSER] Checking browser status');

        const result = await pythonWorker.checkBrowserStatus();

        if (result.status === 'SUCCESS') {
            return res.json({
                success: true,
                browserOpen: result.browserOpen,
                message: result.browserOpen
                    ? 'Browser is open and active'
                    : 'Browser is not open'
            });
        }

        return res.status(500).json({
            success: false,
            error: 'Failed to check browser status',
            data: result
        });

    } catch (error) {
        console.error('[BROWSER] Status check error:', error);

        res.status(500).json({
            success: false,
            error: error.message,
            browserOpen: false
        });
    }
};

module.exports = {
    login,
    submitOtp,
    logout,
    getAuthStatus,
    healthCheck,
    checkBrowserStatus
};