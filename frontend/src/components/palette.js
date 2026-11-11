// Validated categorical order (dataviz reference palette). Values live in CSS variables so light/dark
// each get their own validated steps. Fixed order, never cycled.
export const SERIES = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => `rgb(var(--s${i}))`)
export const OTHER_COLOR = 'rgb(var(--s-other))'
export const GAIN = 'rgb(var(--gain))'
export const LOSS = 'rgb(var(--loss))'
