const TestReport = require('../../infra/models/testReport.model');

const addCommonFields = async (report_id, region, city, inspection_date) => {
    try {
        // Step 1: Find existing record with report_id
        const existingReport = await TestReport.findOne({ report_id });

        if (!existingReport) {
            throw new Error(`Report with ID ${report_id} not found in database`);
        }

        console.log(`Found existing report with ${existingReport.asset_data?.length || 0} assets`);

        // Step 2: Update all assets in asset_data array with common values
        const updatedAssetData = existingReport.asset_data.map(asset => {
            return {
                ...asset, // Preserve all existing asset fields
                region: region || asset.region, // Use provided region or keep existing
                city: city || asset.city, // Use provided city or keep existing
                inspection_date: inspection_date || asset.inspection_date // Use provided date or keep existing
            };
        });

        // Step 3: Update the document
        existingReport.asset_data = updatedAssetData;
        existingReport.updated_at = new Date();

        const saved = await existingReport.save();

        console.log(`Successfully updated report ${report_id} with common fields for ${updatedAssetData.length} assets`);
        console.log(`Common values - Region: ${region}, City: ${city}, Inspection Date: ${inspection_date}`);

        return {
            status: "SUCCESS",
            data: saved,
            message: `Updated ${updatedAssetData.length} assets with common fields`
        };

    } catch (err) {
        console.error("[addCommonFields] error:", err);
        return { status: "FAILED", error: err.message };
    }
};

module.exports = { addCommonFields };