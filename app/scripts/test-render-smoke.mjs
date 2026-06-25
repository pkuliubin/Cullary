import React from 'react';
import { renderToString } from 'react-dom/server';
import App from '../src/App.tsx';

const html = renderToString(React.createElement(App));
if (!html.includes('Cullary')) throw new Error('render missing app title');
if (!html.includes('Open Mock Review')) throw new Error('render missing mock entry action');
if (!html.includes('Local-first culling workbench')) throw new Error('render missing product thesis');
console.log(`react render smoke ok: ${html.length} chars`);
