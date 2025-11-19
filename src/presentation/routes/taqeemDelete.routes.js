const express = require('express');
const router = express.Router();
const {
    deleteTaqeemReport,
    changeTaqeemReportStatus,
    deleteAssetsOnly
} = require('../controllers/taqeemDelete.controller');

router.post('/delete-report', deleteTaqeemReport);
router.post('/change-report-status', changeTaqeemReportStatus);
router.post('/delete-assets', deleteAssetsOnly);

module.exports = router;