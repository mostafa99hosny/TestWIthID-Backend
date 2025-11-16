const express = require('express');
const router = express.Router();

const {
    getAllResourceMetrics,
    discoverAllTabs,
    syncTabs,
    singleTabResourceMetrics,
    startResourceMonitoring,
    stopResourceMonitoring
} = require('../controllers/taqeemResources.controller');


router.get('/resources/metrics', getAllResourceMetrics);
router.get('/tabs/discover', discoverAllTabs);
router.get('/tabs/:tabId/metrics', singleTabResourceMetrics);

router.post('/tabs/sync', syncTabs);
router.post('/resources/monitoring/start', startResourceMonitoring);
router.post('/resources/monitoring/stop', stopResourceMonitoring);


module.exports = router;