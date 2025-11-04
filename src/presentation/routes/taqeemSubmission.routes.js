const express = require('express');
const router = express.Router();
const { validateExcelData, uploadWithoutBaseReportToDB } = require('../controllers/taqeemSubmission.controller');
const upload = require('../../shared/utils/upload');

router.post('/validate-report', validateExcelData);
router.post('/save-without-base', upload.single('excelFile'), uploadWithoutBaseReportToDB);
module.exports = router;