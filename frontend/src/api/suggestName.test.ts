import { expect, test } from 'vitest'
import { suggestNameFromMapsUrl } from './suggestName'

test('extracts the place name from a /maps/place/ URL', () => {
  expect(
    suggestNameFromMapsUrl('https://www.google.com/maps/place/Joes+Coffee/@40.7,-73.9,17z'),
  ).toBe('Joes Coffee')
})

test('decodes percent-encoded characters and keeps readable punctuation', () => {
  expect(
    suggestNameFromMapsUrl("https://www.google.com/maps/place/Joe's%20Coffee%20%26%20Tea"),
  ).toBe("Joe's Coffee & Tea")
})

test('uses the data= name segment when the place path is missing', () => {
  expect(suggestNameFromMapsUrl('https://maps.google.com/?q=Blue+Bottle+Coffee')).toBe(
    'Blue Bottle Coffee',
  )
})

test('returns an empty string for a maps URL without a usable name', () => {
  expect(suggestNameFromMapsUrl('https://www.google.com/maps/@40.7,-73.9,17z')).toBe('')
})

test('returns an empty string for a non-URL input', () => {
  expect(suggestNameFromMapsUrl('not a url')).toBe('')
})

test('returns an empty string for a short share link that carries no name', () => {
  expect(suggestNameFromMapsUrl('https://maps.app.goo.gl/abc123')).toBe('')
})

test('collapses the + separators and trims surrounding whitespace', () => {
  expect(suggestNameFromMapsUrl('https://www.google.com/maps/place/++The++Diner++/')).toBe(
    'The Diner',
  )
})
