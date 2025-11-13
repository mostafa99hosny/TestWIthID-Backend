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

module.exports = {
    deleteTaqeemReport,
    changeTaqeemReportStatus
};