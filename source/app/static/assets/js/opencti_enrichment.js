/**
 * OpenCTI Enrichment Progress Client
 * 
 * Provides real-time WebSocket-based progress updates for OpenCTI enrichment tasks.
 * Uses SocketIO to connect to the /opencti namespace and receive progress events.
 */

class OpenCTIEnrichmentProgress {
    /**
     * Create an OpenCTIEnrichmentProgress instance
     * 
     * @param {Object} options - Configuration options
     * @param {string} options.socketUrl - SocketIO server URL (defaults to window.location.origin)
     * @param {Object} options.socketOptions - SocketIO connection options
     * @param {Function} options.onProgress - Callback for progress updates
     * @param {Function} options.onComplete - Callback for task completion
     * @param {Function} options.onError - Callback for errors
     * @param {Function} options.onConnected - Callback when connected to WebSocket
     * @param {Function} options.onDisconnected - Callback when disconnected
     */
    constructor(options = {}) {
        this.socketUrl = options.socketUrl || window.location.origin;
        this.socketOptions = options.socketOptions || {};
        this.onProgress = options.onProgress || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        this.onConnected = options.onConnected || (() => {});
        this.onDisconnected = options.onDisconnected || (() => {});
        
        this.socket = null;
        this.alertId = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
    }

    /**
     * Connect to the OpenCTI WebSocket namespace
     * 
     * @returns {Promise<void>}
     */
    connect() {
        return new Promise((resolve, reject) => {
            try {
                // Check if SocketIO client is available
                if (typeof io === 'undefined') {
                    console.error('[OpenCTI] SocketIO client not found. Include socket.io.js first.');
                    reject(new Error('SocketIO client not available'));
                    return;
                }

                this.socket = io(`${this.socketUrl}/opencti`, this.socketOptions);

                this.socket.on('connect', () => {
                    console.log('[OpenCTI] Connected to WebSocket');
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    this.onConnected();
                    resolve();
                });

                this.socket.on('disconnect', () => {
                    console.log('[OpenCTI] Disconnected from WebSocket');
                    this.isConnected = false;
                    this.onDisconnected();
                });

                this.socket.on('connect_error', (error) => {
                    console.error('[OpenCTI] Connection error:', error);
                    this.onError({ type: 'connection_error', error: error.message });
                    reject(error);
                });

                this.socket.on('enrichment_progress', (data) => {
                    this._handleProgressEvent(data);
                });

                this.socket.on('error', (data) => {
                    console.error('[OpenCTI] Server error:', data.message);
                    this.onError({ type: 'server_error', message: data.message });
                });

            } catch (error) {
                console.error('[OpenCTI] Failed to connect:', error);
                this.onError({ type: 'connection_failed', error: error.message });
                reject(error);
            }
        });
    }

    /**
     * Disconnect from the WebSocket
     */
    disconnect() {
        if (this.socket) {
            this.leaveEnrichment();
            this.socket.disconnect();
            this.socket = null;
            this.isConnected = false;
        }
    }

    /**
     * Join an enrichment progress room for a specific alert
     * 
     * @param {number} alertId - The alert ID to join progress for
     * @returns {Promise<Object>} Promise resolving to join result
     */
    joinEnrichment(alertId) {
        return new Promise((resolve, reject) => {
            if (!this.isConnected) {
                reject(new Error('Not connected to WebSocket'));
                return;
            }

            if (!alertId) {
                reject(new Error('alertId is required'));
                return;
            }

            this.alertId = alertId;
            
            this.socket.emit('join_enrichment', { alert_id: alertId }, (response) => {
                if (response && response.error) {
                    reject(new Error(response.error));
                } else {
                    console.log(`[OpenCTI] Joined enrichment room for alert ${alertId}`);
                    resolve(response);
                }
            });
        });
    }

    /**
     * Leave the current enrichment progress room
     */
    leaveEnrichment() {
        if (this.alertId && this.socket) {
            this.socket.emit('leave_enrichment', { alert_id: this.alertId });
            console.log(`[OpenCTI] Left enrichment room for alert ${this.alertId}`);
            this.alertId = null;
        }
    }

    /**
     * Get current enrichment progress via REST API (fallback)
     * 
     * @param {number} alertId - The alert ID to get progress for
     * @returns {Promise<Object>} Promise resolving to progress data
     */
    async getProgress(alertId) {
        try {
            const response = await fetch(`/opencti/progress/${alertId}`);
            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                return data.data;
            } else {
                throw new Error(data.message || 'Failed to get progress');
            }
        } catch (error) {
            console.error('[OpenCTI] Failed to get progress:', error);
            throw error;
        }
    }

    /**
     * Trigger enrichment for an alert
     * 
     * @param {number} alertId - The alert ID to enrich
     * @returns {Promise<Object>} Promise resolving to task info
     */
    async triggerEnrichment(alertId) {
        try {
            const response = await fetch(`/opencti/enrich/${alertId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                return data.data;
            } else {
                throw new Error(data.message || 'Failed to trigger enrichment');
            }
        } catch (error) {
            console.error('[OpenCTI] Failed to trigger enrichment:', error);
            throw error;
        }
    }

    /**
     * Handle incoming progress event
     * 
     * @private
     * @param {Object} data - Progress event data
     */
    _handleProgressEvent(data) {
        const { alert_id, progress, status } = data;

        // Only handle events for the current alert
        if (this.alertId && alert_id !== this.alertId) {
            return;
        }

        console.log('[OpenCTI] Progress update:', data);

        // Call progress callback
        this.onProgress(progress);

        // Handle completion states
        if (status === 'completed' || (progress && progress.status === 'success')) {
            this.onComplete(progress);
        } else if (status === 'error' || progress.status === 'error') {
            this.onError({
                type: 'enrichment_error',
                alert_id: alert_id,
                error: progress.error || 'Enrichment failed',
                progress: progress
            });
        }
    }

    /**
     * Get connection status
     * 
     * @returns {boolean}
     */
    isConnected() {
        return this.isConnected;
    }

    /**
     * Get current alert ID
     * 
     * @returns {number|null}
     */
    getAlertId() {
        return this.alertId;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = OpenCTIEnrichmentProgress;
}

// Auto-initialize helper for quick setup
window.OpenCTIEnrichmentProgress = OpenCTIEnrichmentProgress;

/**
 * Quick helper to start listening to enrichment progress
 * 
 * @param {number} alertId - Alert ID to monitor
 * @param {Object} callbacks - Callback functions
 * @returns {OpenCTIEnrichmentProgress}
 */
window.watchOpenCTIEnrichment = function(alertId, callbacks = {}) {
    const progress = new OpenCTIEnrichmentProgress(callbacks);
    
    progress.connect().then(() => {
        progress.joinEnrichment(alertId);
    }).catch(error => {
        console.error('[OpenCTI] Failed to start watching enrichment:', error);
        if (callbacks.onError) {
            callbacks.onError({ type: 'initialization_error', error: error.message });
        }
    });
    
    return progress;
};
