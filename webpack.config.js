// webpack.config.js
// Configuration for bundling minimalist UI JS modules
// Run: npx webpack --mode production

const path = require('path');

module.exports = {
  entry: {
    'minimalist-bundle': [
      './source/app/static/assets/js/minimalist-nav.js',
      './source/app/static/assets/js/zen-mode.js',
      './source/app/static/assets/js/keyboard-nav.js',
      './source/app/static/assets/js/smart-input.js'
    ]
  },
  output: {
    filename: '[name].js',
    path: path.resolve(__dirname, 'source/app/static/assets/js'),
    clean: true
  },
  mode: 'production',
  optimization: {
    minimize: true,
    splitChunks: {
      chunks: 'all',
      minSize: 10000,
      maxSize: 100000
    }
  },
  performance: {
    maxEntrypointSize: 102400, // 100KB
    maxAssetSize: 102400, // 100KB
    hints: 'warning'
  },
  stats: {
    chunks: false,
    modules: false,
    colors: true,
    size: true
  }
};
