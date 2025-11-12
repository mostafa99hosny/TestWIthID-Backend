const pythonWorker = require('../../scripts/core/pythonWorker/index');
const { noBaseDataExtraction } = require('../../app/equipment/noBaseExtraction');
const { addCommonFields } = require('../../app/equipment/addCommonFields');

const validateExcelData = async (req, res) => {
    try {
        const { reportId } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[VALIDATION] Starting validation for report: ${reportId}`);

        const result = await pythonWorker.validateExcelData(reportId);

        res.json({ data: result });

    } catch (error) {
        console.error('[VALIDATION] Validation error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
};

const uploadWithoutBaseReportToDB = async (req, res) => {
    try {
        // Check if file was uploaded
        if (!req.file) {
            return res.status(400).json({
                status: "FAILED",
                error: "No Excel file uploaded"
            });
        }

        // Extract all required fields from request body
        const { reportId } = req.body;

        // Validate required fields
        if (!reportId) {
            return res.status(400).json({
                status: "FAILED",
                error: "Report ID is required"
            });
        }

        const excelFilePath = req.file.path; // Get the path from uploaded file

        // Pass all parameters to extraction function
        const result = await noBaseDataExtraction(excelFilePath, reportId);

        return res.json({ data: result });
    } catch (err) {
        console.error("[uploadWithoutBaseReportToDB] error:", err);
        return res.status(500).json({
            status: "FAILED",
            error: err.message
        });
    }
};

const createAssets = async (req, res) => {
    try {
        const { reportId, macroCount, tabsNum } = req.body;

        // Validate required fields
        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        if (!macroCount || macroCount <= 0) {
            return res.status(400).json({
                success: false,
                error: 'Valid macro count is required'
            });
        }

        console.log(`[ASSET CREATION] Starting asset creation for report: ${reportId}, count: ${macroCount}, tabs: ${tabsNum || 3}`);

        // Call Python worker to create assets
        const result = await pythonWorker.createAssets(
            reportId,
            macroCount,
            tabsNum || 3,
        );

        // Check if creation was successful
        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result
            });
        } else if (result.status === 'STOPPED') {
            res.status(200).json({
                success: false,
                stopped: true,
                message: result.message || 'Asset creation was stopped by user',
                data: result
            });
        } else {
            res.status(400).json({
                success: false,
                error: result.error || 'Failed to create assets',
                data: result
            });
        }

    } catch (error) {
        console.error('[ASSET CREATION] Error:', error);
        const statusCode = error.message?.includes('timeout') ? 504 : 500;
        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
};

const grabMacroIds = async (req, res) => {
    try {
        const { reportId, tabsNum } = req.body;

        // Validate required fields
        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[GRAB MACRO IDS] Starting to grab macro IDs for report: ${reportId}, tabs: ${tabsNum || 3}`);

        // Call Python worker to grab macro IDs
        const result = await pythonWorker.grabMacroIds(
            reportId,
            tabsNum || 3,
        );

        console.log('[GRAB MACRO IDS] Result:', result);

        // Check if grabbing was successful
        if (result.status === 'SUCCESS') {
            res.json({
                success: true,
                data: result
            });
        } else {
            res.status(400).json({
                success: false,
                error: result.error || 'Failed to grab macro IDs',
                data: result
            });
        }

    } catch (error) {
        console.error('[GRAB MACRO IDS] Error:', error);
        const statusCode = error.message?.includes('timeout') ? 504 : 500;
        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
}

const addCommonFieldsToAssets = async (req, res) => {
    try {
        const { reportId, region, city, inspectionDate } = req.body;
        const result = await addCommonFields(reportId, region, city, inspectionDate);

        res.json(result);
    } catch (error) {
        console.error('[ADD COMMON FIELDS] Error:', error);
        res.status(500).json({
            status: "FAILED",
            error: error.message
        });
    }
}

const pauseProcessing = async (req, res) => {
    try {
        const { reportId } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[PAUSE] Pausing processing for report: ${reportId}`);

        const result = await pythonWorker.pauseProcessing(reportId);

        if (result.status === 'PAUSED') {
            res.json({
                success: true,
                data: result
            });
        } else {
            res.status(400).json({
                success: false,
                error: result.error || 'Failed to pause processing',
                data: result
            });
        }

    } catch (error) {
        console.error('[PAUSE] Error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const resumeProcessing = async (req, res) => {
    try {
        const { reportId } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[RESUME] Resuming processing for report: ${reportId}`);

        const result = await pythonWorker.resumeProcessing(reportId);

        if (result.status === 'RESUMED') {
            res.json({
                success: true,
                data: result
            });
        } else {
            res.status(400).json({
                success: false,
                error: result.error || 'Failed to resume processing',
                data: result
            });
        }

    } catch (error) {
        console.error('[RESUME] Error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

const editMacros = async (req, res) => {
    try {
        const { reportId, tabsNum } = req.body;
        const result = await pythonWorker.editMacros(reportId, tabsNum);

        return result;
    } catch (error) {
        console.error('[EDIT MACROS] Error:', error);
        throw error;
    }
};

const checkMacroStatus = async (req, res) => {
    try {
        const { reportId, tabsNum } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[CHECK MACRO STATUS] Starting check for report: ${reportId}, tabs: ${tabsNum || 3}`);

        const result = await pythonWorker.checkMacroStatus(reportId, tabsNum || 3);

        res.json({ data: result });

    } catch (error) {
        console.error('[CHECK MACRO STATUS] Error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
}

const halfCheckMacroStatus = async (req, res) => {
    try {
        const { reportId, tabsNum } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[HALF CHECK MACRO STATUS] Starting half-check for report: ${reportId}, tabs: ${tabsNum || 3}`);

        const result = await pythonWorker.halfCheckMacroStatus(reportId, tabsNum || 3);

        res.json({ data: result });

    } catch (error) {
        console.error('[HALF CHECK MACRO STATUS] Error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
};

module.exports = {
    validateExcelData,
    uploadWithoutBaseReportToDB,
    createAssets,
    grabMacroIds,
    addCommonFieldsToAssets,
    editMacros,
    checkMacroStatus,
    halfCheckMacroStatus,
    resumeProcessing,
    pauseProcessing
};