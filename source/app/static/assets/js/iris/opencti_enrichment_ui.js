/**
 * OpenCTI Enrichment Integration for Alerts Page
 * 
 * Integrates real-time WebSocket progress updates with the enrichment modal.
 */

let openctiProgressTracker = null;
let currentEnrichmentAlertId = null;

/**
 * Initialize OpenCTI enrichment progress tracking
 */
function initOpenCTIEnrichment() {
    if (openctiProgressTracker) {
        return;
    }

    // Create progress tracker instance
    openctiProgressTracker = new OpenCTIEnrichmentProgress({
        onConnected: function() {
            console.log('[IRIS] Connected to OpenCTI WebSocket');
        },
        onDisconnected: function() {
            console.log('[IRIS] Disconnected from OpenCTI WebSocket');
        },
        onProgress: function(progress) {
            updateEnrichmentProgressUI(progress);
        },
        onComplete: function(progress) {
            console.log('[IRIS] Enrichment completed', progress);
            updateEnrichmentProgressUI(progress);
            hideProgressBar();
            
            // Show success notification
            if (progress && progress.status === 'success') {
                notify_success('OpenCTI enrichment completed successfully');
            }
        },
        onError: function(error) {
            console.error('[IRIS] OpenCTI error:', error);
            
            if (error.type === 'enrichment_error') {
                notify_error(`Enrichment failed: ${error.error}`);
            } else if (error.type === 'connection_error') {
                notify_warning('WebSocket disconnected. Progress updates may be delayed.');
            } else {
                notify_error(`OpenCTI error: ${error.message || error.error}`);
            }
        }
    });

    // Connect to WebSocket
    openctiProgressTracker.connect().catch(error => {
        console.error('[IRIS] Failed to connect to OpenCTI WebSocket:', error);
    });
}

/**
 * Show the enrichment progress bar
 */
function showProgressBar() {
    $('#enrichmentProgressSection').show();
    $('#enrichmentProgressBar').addClass('progress-bar-animated');
    $('#enrichmentProgressBar').removeClass('bg-success bg-danger bg-warning');
}

/**
 * Hide the enrichment progress bar
 */
function hideProgressBar() {
    $('#enrichmentProgressSection').hide();
    $('#enrichmentProgressBar').removeClass('progress-bar-animated');
}

/**
 * Update the enrichment progress UI
 * 
 * @param {Object} progress - Progress data from WebSocket
 */
function updateEnrichmentProgressUI(progress) {
    if (!progress) {
        return;
    }

    showProgressBar();

    const total = progress.total || 0;
    const processed = progress.processed || 0;
    const matched = progress.matched || 0;
    const noMatch = progress.no_match || 0;
    const errors = progress.errors || 0;
    const currentIOC = progress.current_ioc;
    const status = progress.status || 'unknown';

    // Calculate percentage
    let percentage = 0;
    if (total > 0) {
        percentage = Math.round((processed / total) * 100);
    }

    // Update progress bar
    const progressBar = $('#enrichmentProgressBar');
    progressBar.css('width', percentage + '%');
    progressBar.attr('aria-valuenow', percentage);
    $('#enrichmentProgressText').text(percentage + '%');

    // Update details
    $('#progressTotal').text(total);
    $('#progressProcessed').text(processed);
    $('#progressMatched').text(matched);
    $('#progressErrors').text(errors);

    // Update current IOC
    if (currentIOC) {
        $('#progressCurrentIOC').show();
        $('#currentIOCValue').text(currentIOC);
    } else {
        $('#progressCurrentIOC').hide();
    }

    // Update status badge
    const statusBadge = $('#statusBadge');
    const statusDiv = $('#progressStatus');
    
    statusDiv.show();
    statusBadge.removeClass('progress-status-running progress-status-success progress-status-partial progress-status-error progress-status-skipped');
    
    switch (status) {
        case 'running':
            statusBadge.addClass('progress-status-running');
            statusBadge.text('Running');
            break;
        case 'success':
            statusBadge.addClass('progress-status-success');
            statusBadge.text('Completed');
            break;
        case 'partial':
            statusBadge.addClass('progress-status-partial');
            statusBadge.text('Completed with errors');
            break;
        case 'error':
            statusBadge.addClass('progress-status-error');
            statusBadge.text('Error');
            break;
        case 'skipped':
            statusBadge.addClass('progress-status-skipped');
            statusBadge.text('Skipped');
            break;
        default:
            statusBadge.text(status);
    }

    // Stop animation on completion
    if (status === 'success' || status === 'error' || status === 'partial' || status === 'skipped') {
        progressBar.removeClass('progress-bar-animated');
    }
}

/**
 * Join enrichment room for a specific alert
 * 
 * @param {number} alertId - Alert ID to join
 */
function joinEnrichmentRoom(alertId) {
    if (!openctiProgressTracker) {
        initOpenCTIEnrichment();
    }

    currentEnrichmentAlertId = alertId;

    openctiProgressTracker.joinEnrichment(alertId)
        .then(() => {
            console.log('[IRIS] Joined enrichment room for alert', alertId);
        })
        .catch(error => {
            console.error('[IRIS] Failed to join enrichment room:', error);
        });
}

/**
 * Leave current enrichment room
 */
function leaveEnrichmentRoom() {
    if (openctiProgressTracker && currentEnrichmentAlertId) {
        openctiProgressTracker.leaveEnrichment();
        currentEnrichmentAlertId = null;
    }
}

/**
 * Trigger enrichment for an alert
 * 
 * @param {number} alertId - Alert ID to enrich
 */
async function triggerOpenCTIEnrichment(alertId) {
    try {
        // Join the progress room first
        joinEnrichmentRoom(alertId);
        
        // Show progress UI
        showProgressBar();
        $('#enrichmentProgressBar').addClass('progress-bar-animated');
        
        // Trigger the enrichment task
        const data = await openctiProgressTracker.triggerEnrichment(alertId);
        
        console.log('[IRIS] Enrichment triggered:', data);
        
        if (data.auto_enrich) {
            notify_info('Auto-enrichment is already enabled for this alert');
        } else {
            notify_success('Enrichment task started. Progress will be shown below.');
        }
        
    } catch (error) {
        console.error('[IRIS] Failed to trigger enrichment:', error);
        notify_error(`Failed to start enrichment: ${error.message}`);
    }
}

// Initialize on document ready
$(document).ready(function() {
    // Initialize OpenCTI enrichment when page loads
    initOpenCTIEnrichment();

    // Handle trigger enrichment button
    $('#triggerEnrichmentBtn').on('click', function() {
        const alertId = $(this).data('alert-id');
        if (alertId) {
            triggerOpenCTIEnrichment(alertId);
        }
    });

    // Leave enrichment room when modal closes
    $('#enrichmentModal').on('hidden.bs.modal', function() {
        leaveEnrichmentRoom();
        hideProgressBar();
    });
});
