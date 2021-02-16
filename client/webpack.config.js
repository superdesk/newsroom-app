const path = require('path');
const newsroomWebpack = require('newsroom-core/webpack.config')

for (const [name, path] of Object.entries(newsroomWebpack.entry)) {
    if (Array.isArray(path)) {
        newsroomWebpack.entry[name] = path.map(f => `./node_modules/newsroom-core/node_modules/${f}`)
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
        path: path.resolve(__dirname, 'dist'),
        publicPath: 'http://localhost:8080/',
        filename: '[name].[chunkhash].js',
        chunkFilename: '[id].[chunkhash].js'
    },
    resolve: {
        ...newsroomWebpack.resolve,
        modules: [
            ...newsroomWebpack.resolve.modules,
            './node_modules',
            path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules'),
            path.resolve(__dirname, 'node_modules', 'newsroom-core', 'assets')
        ]
    },
    resolveLoader: {
        modules: [
            './node_modules',
            path.resolve(__dirname, 'node_modules', 'newsroom-core', 'node_modules'),
        ]
    }
};

