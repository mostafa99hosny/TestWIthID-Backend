const express = require('express');
const router = express.Router();
const { deleteTaqeemReport } = require('../controllers/taqeemDelete.controller');

router.post('/delete-report', deleteTaqeemReport);

module.exports = router;