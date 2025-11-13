const express = require('express');
const router = express.Router();
const authController = require('../controllers/taqeemAuth.controller');

router.post('/login', authController.login);
router.post('/otp', authController.submitOtp);
router.post('/logout', authController.logout);

router.get('/status', authController.getAuthStatus);

router.get('/browser/status', authController.checkBrowserStatus);
router.post('/browser/new-window', authController.createNewWindow);

module.exports = router;