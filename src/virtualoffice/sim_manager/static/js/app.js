// Entry point for VDOS dashboard (ES modules)
// Keep this lightweight: import feature bundles in place.

// Import the existing dashboard logic as a module so it runs on load
import './dashboard.js';

// In future steps, we will replace the monolith with modular imports like:
// import './core/refresh.js';
// import './features/emails/index.js';
// import './features/chat/index.js';
// etc.

