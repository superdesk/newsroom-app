const path = require('path');
const fs = require('fs');
const config = require('newsroom-core/webpack.config')

// modify webpack paths to serve them from modules folder
for (const [name, path] of Object.entries(config.entry)) {
    if (Array.isArray(path)) {
        // common modules
        if (fs.existsSync('node_modules/newsroom-core/node_modules')) {
            // when using linked repo
            config.entry[name] = path.map(f => `./node_modules/newsroom-core/node_modules/${f}`)
        } else {
            // when using npm package
            config.entry[name] = path.map(f => `./node_modules/${f}`)
        }
    } else {
        config.entry[name] = `./node_modules/newsroom-core/${path}`
    }
}

config.entry.app = './app.js'
config.output.path = path.resolve(__dirname, 'dist')
config.resolve.modules.push(
    path.resolve(__dirname, 'node_modules'),
    path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules')
)
config.resolveLoader.modules.push(
    path.resolve(__dirname, 'node_modules'),
    path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules'),
)

module.exports = config
