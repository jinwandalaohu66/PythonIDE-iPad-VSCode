const readings = [18, 21, 24]
const mean = readings.reduce((sum, value) => sum + value, 0) / readings.length
console.log('Mean:', mean)
