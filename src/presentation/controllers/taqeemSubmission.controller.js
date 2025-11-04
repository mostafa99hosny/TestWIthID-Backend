const pythonWorker = require('../../scripts/core/pythonWorker/index');
const { noBaseDataExtraction } = require('../../app/equipment/noBaseExtraction');

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
        const { reportId, region, city, inspectionDate } = req.body;

        // Validate required fields
        if (!reportId) {
            return res.status(400).json({
                status: "FAILED",
                error: "Report ID is required"
            });
        }

        if (!region) {
            return res.status(400).json({
                status: "FAILED",
                error: "Region is required"
            });
        }

        if (!city) {
            return res.status(400).json({
                status: "FAILED",
                error: "City is required"
            });
        }

        if (!inspectionDate) {
            return res.status(400).json({
                status: "FAILED",
                error: "Inspection date is required"
            });
        }

        const excelFilePath = req.file.path; // Get the path from uploaded file

        // Get userId from authenticated user (adjust based on your auth setup)
        const userId = req.user?.id || req.userId || null;

        // Pass all parameters to extraction function
        const result = await noBaseDataExtraction(
            excelFilePath,
            reportId,
            userId,
            region,
            city,
            inspectionDate
        );

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



module.exports = {
    validateExcelData,
    uploadWithoutBaseReportToDB,
    createAssets
};