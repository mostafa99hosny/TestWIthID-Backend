const pythonWorker = require('../../scripts/core/pythonWorker/index');

const deleteTaqeemReport = async (req, res) => {
    try {
        const { reportId } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[DELETE REPORT] Starting deletion for report: ${reportId}`);

        const result = await pythonWorker.deleteReport(reportId);

        res.json({ data: result });

    } catch (error) {
        console.error('[DELETE REPORT] Deletion error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
}

const changeTaqeemReportStatus = async (req, res) => {
    try {
        const { reportId } = req.body;

        if (!reportId) {
            return res.status(400).json({
                success: false,
                error: 'Report ID is required'
            });
        }

        console.log(`[CHANGE REPORT STATUS] Changing status for report: ${reportId}`);

        const result = await pythonWorker.handleCancelledReport(reportId);

        res.json({ data: result });

    } catch (error) {
        console.error('[CHANGE REPORT STATUS] Error:', error);

        const statusCode = error.message?.includes('timeout') ? 504 : 500;

        res.status(statusCode).json({
            success: false,
            error: error.message,
            isTimeout: error.message?.includes('timeout')
        });
    }
}

const deleteAssetsOnly = async (req, res) => {
    const { reportId, batchId } = req.body;

    if (!reportId) {
        return res.status(400).json({
            success: false,
            error: 'Report ID is required'
        });
    }

    try {

        const result = await pythonWorker.deleteIncompleteAssets(reportId, batchId);

        if (result.status === 'SUCCESS') {
            return res.json({
                success: true,
                message: result.message,
                data: {
                    reportId: result.reportId,
                    totalDeleted: result.data.total_deleted,
                    mainPagesProcessed: result.data.main_pages_processed
                }
            });
        } else if (result.status === 'STOPPED') {
            return res.json({
                success: false,
                stopped: true,
                message: result.message,
                reportId: result.reportId
            });
        } else {
            return res.status(500).json({
                success: false,
                error: result.error || 'Failed to delete incomplete assets',
                reportId: result.reportId
            });
        }

    } catch (error) {
        console.error('[API] Error deleting incomplete assets:', error);
        return res.status(500).json({
            success: false,
            error: error.message || 'Internal server error'
        });
    }
};

module.exports = {
    deleteTaqeemReport,
    changeTaqeemReportStatus,
    deleteAssetsOnly
};