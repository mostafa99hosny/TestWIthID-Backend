const express = require('express');
const router = express.Router();
const { validateExcelData, uploadWithoutBaseReportToDB, createAssets, grabMacroIds } = require('../controllers/taqeemSubmission.controller');
const upload = require('../../shared/utils/upload');

router.post('/validate-report', validateExcelData);
router.post('/save-without-base', upload.single('excelFile'), uploadWithoutBaseReportToDB);
router.post('/create-assets', createAssets);
router.post('/grab-macro-ids', grabMacroIds);

module.exports = router; 