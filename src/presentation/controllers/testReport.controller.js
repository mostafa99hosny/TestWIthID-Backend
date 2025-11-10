const TestReport = require('../../infra/models/testReport.model');

// GET /api/reports/by-number/:reportId
exports.getReportByNumber = async (req, res) => {
  try {
    const reportId = req.params.reportId;

    if (!reportId) {
      return res.status(400).json({ success: false, message: "Report ID is required" });
    }

    // findOne by report_id field (not _id)
    const report = await TestReport.findOne({ report_id: reportId }).lean();

    if (!report) {
      return res.status(404).json({ success: false, message: "Report not found" });
    }

    return res.status(200).json({
      success: true,
      data: report,
    });
  } catch (error) {
    console.error("Error in getReportByNumber:", error);
    return res.status(500).json({
      success: false,
      message: "Server error while fetching report",
    });
  }
};
