const path = require('path');
const fs = require('fs');
const newsroomWebpack = require('newsroom-core/webpack.config')

for (const [name, path] of Object.entries(newsroomWebpack.entry)) {
    if (Array.isArray(path)) {
        // common modules
        if (fs.existsSync('node_modules/newsroom-core/node_modules')) {
            // when using linked repo
            newsroomWebpack.entry[name] = path.map(f => `./node_modules/newsroom-core/node_modules/${f}`)
        } else {
            // when using npm package
            newsroomWebpack.entry[name] = path.map(f => `./node_modules/${f}`)
        }
    } else {
        newsroomWebpack.entry[name] = `./node_modules/newsroom-core/${path}`
    }
}

module.exports = {
    ...newsroomWebpack,
    entry: {
        ...newsroomWebpack.entry,
        app: './app.js'
    },
    output: {
        ...newsroomWebpack.output,
        path: path.resolve(__dirname, 'dist')
    },
    resolve: {
        ...newsroomWebpack.resolve,
        modules: [
            ...newsroomWebpack.resolve.modules,
            path.resolve(__dirname, 'node_modules'),
            path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules'),
        ]
    },
    resolveLoader: {
        ...newsroomWebpack.resolveLoader,
        modules: [
            path.resolve(__dirname, 'node_modules'),
            path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules'),
        ]
    }
};
