module.exports = {
  env: { browser: true, es2020: true },
  extends: ['eslint:recommended', 'plugin:react/recommended'],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react'],
  settings: { react: { version: 'detect' } },
  rules: {
    'react/prop-types': 'off',
    'react/react-in-jsx-scope': 'off'
  }
}
