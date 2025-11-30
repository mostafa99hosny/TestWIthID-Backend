const pythonWorker = require("../../scripts/core/pythonWorker/index");

const getAllResourceMetrics = async (req, res) => {
    try {
        const result = await pythonWorker.getAllResourceMetrics(true);

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result.data,
                timestamp: new Date().toISOString()
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to get resource metrics'
            });
        }
    } catch (error) {
        console.error('[API] Error getting resource metrics:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const discoverAllTabs = async (req, res) => {
    try {
        const result = await pythonWorker.discoverAllTabs();

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result.data
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to discover tabs'
            });
        }
    } catch (error) {
        console.error('[API] Error discovering tabs:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};


const syncTabs = async (req, res) => {
    try {
        const result = await pythonWorker.syncTabs();

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result.data
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to sync tabs'
            });
        }
    } catch (error) {
        console.error('[API] Error syncing tabs:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};


const singleTabResourceMetrics = async (req, res) => {
    try {
        const { tabId } = req.params;

        if (!tabId) {
            return res.status(400).json({
                success: false,
                error: 'Tab ID is required'
            });
        }

        const result = await pythonWorker.getTabResourceMetrics(tabId, true);

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result.data,
                timestamp: new Date().toISOString()
            });
        } else {
            res.status(404).json({
                success: false,
                error: result.error || 'Tab not found'
            });
        }
    } catch (error) {
        console.error(`[API] Error getting metrics for tab ${req.params.tabId}:`, error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const startResourceMonitoring = async (req, res) => {
    try {
        const { interval = 5 } = req.body;
        const result = await pythonWorker.startResourceMonitoring(interval);

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                message: 'Resource monitoring started',
                interval
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to start monitoring'
            });
        }
    } catch (error) {
        console.error('[API] Error starting resource monitoring:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const stopResourceMonitoring = async (req, res) => {
    try {
        const result = await pythonWorker.stopResourceMonitoring();

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                message: 'Resource monitoring stopped'
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to stop monitoring'
            });
        }
    } catch (error) {
        console.error('[API] Error stopping resource monitoring:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const getCompanies = async (req, res) => {
    try {
        const result = await pythonWorker.getCompanies();

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result.data,
                timestamp: new Date().toISOString()
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to get companies'
            });
        }
    } catch (error) {
        console.error('[API] Error getting companies:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const navigateToCompany = async (req, res) => {
    try {
        const { url, radius = 0 } = req.body;

        if (!url) {
            return res.status(400).json({
                success: false,
                error: 'URL is required'
            });
        }

        const result = await pythonWorker.navigateToCompany(url, radius);

        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                message: result.message,
                url: result.url,
                radius: result.radius,
                timestamp: new Date().toISOString()
            });
        } else {
            res.status(500).json({
                success: false,
                error: result.error || 'Failed to navigate to company'
            });
        }
    } catch (error) {
        console.error('[API] Error navigating to company:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};


module.exports = {
    getAllResourceMetrics,
    discoverAllTabs,
    syncTabs,
    singleTabResourceMetrics,
    startResourceMonitoring,
    stopResourceMonitoring,
    getCompanies,
    navigateToCompany
};
