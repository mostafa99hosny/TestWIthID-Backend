const express = require('express');
const router = express.Router();
const { getReportByNumber } = require('../controllers/testReport.controller');

// Example: GET /api/reports/by-number/123456
router.get('/by-number/:reportId', getReportByNumber);

module.exports = router;
