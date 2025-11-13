const express = require('express');
const router = express.Router();
const { deleteTaqeemReport, changeTaqeemReportStatus } = require('../controllers/taqeemDelete.controller');

router.post('/delete-report', deleteTaqeemReport);
router.post('/change-report-status', changeTaqeemReportStatus);

module.exports = router;