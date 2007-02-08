#!/usr/bin/python
#
# Urwid canvas class and functions
#    Copyright (C) 2004-2007  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

from __future__ import generators
import weakref

from util import *
from escape import * 

class CanvasCache(object):
	_widgets = {}
	_refs = {}
	hits = 0
	fetches = 0
	cleanups = 0

	def store(cls, widget, size, focus, canvas):
		"""
		Store a weakref to canvas in the cache.
		"""
		ref = weakref.ref(canvas, cls.cleanup)
		cls._refs[ref] = (widget, size, focus)
		cls._widgets.setdefault(widget, {})[(size, focus)] = ref
	store = classmethod(store)

	def fetch(cls, widget, size, focus):
		"""
		Return the cached canvas for (widget, size, focus) or None.
		"""
		cls.fetches += 1
		sizes = cls._widgets.get(widget, None)
		if not sizes:
			return None
		ref = sizes.get((size, focus), None)
		if not ref:
			return None
		canv = ref()
		if canv:
			cls.hits += 1
		return canv
	fetch = classmethod(fetch)
	
	def invalidate(cls, widget):
		"""
		Remove all canvases cached for widget.
		"""
		try:
			for ref in cls._widgets[widget].values():
				try:
					del cls._refs[ref]
				except KeyError:
					pass
			del cls._widgets[widget]
		except KeyError:
			pass
	invalidate = classmethod(invalidate)

	def cleanup(cls, ref):
		cls.cleanups += 1
		w = cls._refs.get(ref, None)
		if not w:
			return
		widget, size, focus = w
		sizes = cls._widgets.get(widget, None)
		if not sizes:
			return
		try:
			del sizes[(size, focus)]
		except KeyError:
			pass
		if not sizes:
			try:
				del cls._widgets[widget]
			except KeyError:
				pass
		del cls._refs[ref]
	cleanup = classmethod(cleanup)

	def clear(cls):
		"""
		Empty the cache.
		"""
		cls._widgets = {}
		cls._refs = {}
	clear = classmethod(clear)

		
class CanvasError(Exception):
	pass

class Canvas(object):
	"""
	class for storing rendered text and attributes
	"""
	def __init__(self,text = None,attr = None, cs = None, 
		cursor = None, maxcol=None, check_width=True):
		"""
		text -- list of strings, one for each line
		attr -- list of run length encoded attributes for text
		cs -- list of run length encoded character set for text
		cursor -- (x,y) of cursor or None
		maxcol -- screen columns taken by this canvas
		"""
		if text == None: 
			text = []

		if check_width:
			widths = []
			for t in text:
				if type(t) != type(""):
					raise CanvasError("Canvas text must be plain strings encoded in the screen's encoding", `text`)
				widths.append( calc_width( t, 0, len(t)) )
		else:
			assert type(maxcol) == type(0)
			widths = [maxcol] * len(text)

		if maxcol is None:
			if widths:
				# find maxcol ourselves
				maxcol = max(widths)
			else:
				maxcol = 0

		if attr == None: 
			attr = [[] for x in range(len(text))]
		if cs == None:
			cs = [[] for x in range(len(text))]
		
		# pad text and attr to maxcol
		for i in range(len(text)):
			w = widths[i]
			if w > maxcol: 
				raise CanvasError("Canvas text is wider than the maxcol specified \n%s\n%s\n%s"%(`maxcol`,`widths`,`text`))
			if w < maxcol:
				text[i] = text[i] + " "*(maxcol-w)
			a_gap = len(text[i]) - rle_len( attr[i] )
			if a_gap < 0:
				raise CanvasError("Attribute extends beyond text \n%s\n%s" % (`text[i]`,`attr[i]`) )
			if a_gap:
				rle_append_modify( attr[i], (None, a_gap))
			
			cs_gap = len(text[i]) - rle_len( cs[i] )
			if cs_gap < 0:
				raise CanvasError("Character Set extends beyond text \n%s\n%s" % (`text[i]`,`cs[i]`) )
			if cs_gap:
				rle_append_modify( cs[i], (None, cs_gap))
			
		self._attr = attr
		self._cs = cs
		self.cursor = cursor
		self._text = text
		self._maxcol = maxcol

	def rows(self):
		"""Return the number of rows in this canvas."""
		return len(self._text)

	def cols(self):
		"""Return the screen column width of this canvas."""
		return self._maxcol
	
	def translated_coords(self,dx,dy):
		"""
		Return cursor coords shifted by (dx, dy), or None if there
		is no cursor.
		"""
		if self.cursor:
			x, y = self.cursor
			return x+dx, y+dy
		return None

	def content(self, trim_left=0, trim_top=0, cols=None, rows=None,
			def_attr=None):
		"""
		Return the canvas content as a list of rows where each row
		is a list of (attr, cs, text) tuples.

		trim_left, trim_top, cols, rows may be set by 
		CompositeCanvas when rendering a partially obscured
		canvas.
		"""
		maxcol, maxrow = self.cols(), self.rows()
		if not cols: 
			cols = maxcol - trim_left
		if not rows:
			rows = maxrow - trim_top
			
		assert trim_left >= 0 and trim_left < maxcol
		assert cols > 0 and trim_left + cols <= maxcol
		assert trim_top >=0 and trim_top < maxrow
		assert rows > 0 and trim_top + rows <= maxrow
		
		if trim_top or rows < maxrow:
			text_attr_cs = zip(
				self._text[trim_top:trim_top+rows],
				self._attr[trim_top:trim_top+rows], 
				self._cs[trim_top:trim_top+rows])
		else:
			text_attr_cs = zip(self._text, self._attr, self._cs)
		
		for text, a_row, cs_row in text_attr_cs:
			if trim_left or cols < self._maxcol:
				text, a_row, cs_row = trim_text_attr_cs(
					text, a_row, cs_row, trim_left, 
					trim_left + cols)
			attr_cs = util.rle_product(a_row, cs_row)
			i = 0
			row = []
			for (a, cs), run in attr_cs:
				if a is None:
					a = def_attr
				row.append((a, cs, text[i:i+run]))
				i += run
			yield row
			

	def content_delta(self, other):
		"""
		Return the differences between other and this canvas.

		If other is the same object as self this will return no 
		differences, otherwise this is the same as calling 
		content().
		"""
		if other is self:
			return [self.cols()]*self.rows()
		return self.content()
	


class BlankCanvas(object):
	"""
	a canvas with nothing on it, only works as part of a composite canvas
	since it doesn't know its own size
	"""

	def content(self, trim_left, trim_top, cols, rows, attr):
		"""
		return (cols, rows) of spaces with def_attr attribute.
		"""
		line = [(attr, None, " "*cols)]
		for i in range(rows):
			yield line

	def cols(self):
		raise NotImplementedError("BlankCanvas doesn't know its own size!")

	def rows(self):
		raise NotImplementedError("BlankCanvas doesn't know its own size!")
	
	def content_delta(self):
		raise NotImplementedError("BlankCanvas doesn't know its own size!")
		

blank_canvas = BlankCanvas()


class SolidCanvas(object):
	"""
	A canvas filled completely with a single character.
	"""
	def __init__(self, fill_char, cols, rows):
		canv = Canvas([fill_char])
		attr, self.cs, self.text = list(canv.content(0,0,1,1))[0][0]
		self.size = cols, rows
		self.cursor = None
	
	def cols(self):
		return self.size[0]
	
	def rows(self):
		return self.size[1]

	def content(self, trim_left=0, trim_top=0, cols=None, rows=None, 
			attr=None):
		if cols is None:
			cols = self.size[0]
		if rows is None:
			rows = self.size[1]

		line = [(attr, self.cs, self.text*cols)]
		for i in range(rows):
			yield line

	def content_delta(self, other):
		"""
		Return the differences between other and this canvas.
		"""
		if other is self:
			return [self.cols()]*self.rows()
		return self.content()
		



class CompositeCanvas(object):
	"""
	class for storing a combination of canvases
	"""
	def __init__(self, canv=None):
		"""
		canv -- a Canvas object to wrap this CompositeCanvas around.

		if canv is a CompositeCanvas, make a copy of its contents
		"""
		# a "shard" is a (num_rows, list of cviews) tuple, one for 
		# each cview starting in this shard

		# a "cview" is a tuple that defines a view of a canvas:
		# (trim_left, trim_top, cols, rows, def_attr, canv, widget)

		# a "shard tail" is a list of tuples:
		# (col_gap, done_rows, content_iter, cview) 
		
		# tuples that define the unfinished cviews that are part of
		# shards following the first shard.

		if canv is None:
			self.shards = []
			self.cursor = None
		elif hasattr(canv, "shards"):
			self.shards = canv.shards
			self.cursor = canv.cursor
		else:
			self.shards = [(canv.rows(), 
				[(0, 0, canv.cols(), canv.rows(), None, canv)])]
			self.cursor = canv.cursor


	def rows(self):
		return sum(r for r,cv in self.shards)

	def cols(self):
		if not self.shards:
			return 0
		return sum([cv[2] for cv in self.shards[0][1]])

		
	def content(self):
		"""
		Return the canvas content as a list of rows where each row
		is a list of (attr, cs, text) tuples.
		"""
		shard_tail = []
		for num_rows, cviews in self.shards:
			# combine shard and shard tail
			sbody = shard_body(cviews, shard_tail)

			# output rows
			for i in range(num_rows):
				yield shard_body_row(sbody)

			# prepare next shard tail			
			shard_tail = shard_body_tail(num_rows, sbody)

					
	
	def content_delta(self, other):
		"""
		Return the differences between other and this canvas.
		"""
		if not hasattr(other, 'shards'):
			for row in self.content():
				yield row
			return

		shard_tail = []
		for num_rows, cviews in shards_delta(
				self.shards, other.shards):
			# combine shard and shard tail
			sbody = shard_body(cviews, shard_tail)

			# output rows
			row = []
			for i in range(num_rows):
				# if whole shard is unchanged, don't keep 
				# calling shard_body_row
				if len(row) != 1 or type(row[0]) != type(0):
					row = shard_body_row(sbody)
				yield row

			# prepare next shard tail
			shard_tail = shard_body_tail(num_rows, sbody)
				
	
	def trim(self, top, count=None):
		"""Trim lines from the top and/or bottom of canvas.

		top -- number of lines to remove from top
		count -- number of lines to keep, or None for all the rest
		"""
		assert top >= 0, "invalid trim amount %d!"%top
		assert top < self.rows(), "cannot trim %d lines from %d!"%(
			top, self.rows())
		
		if top:
			self.shards = shards_trim_top(self.shards, top)

		if count is not None:
			self.shards = shards_trim_rows(self.shards, count)

		self.translate_coords(0, -top)

		
	def trim_end(self, end):
		"""Trim lines from the bottom of the canvas.
		
		end -- number of lines to remove from the end
		"""
		assert end > 0, "invalid trim amount %d!"%end
		assert end < self.rows(), "cannot trim %d lines from %d!"%(
			end, self.rows())
		
		self.shards = shards_trim_rows(self.shards, self.rows() - end)

			
	def pad_trim_left_right(self, left, right):
		"""
		Pad or trim this canvas on the left and right
		
		values > 0 indicate screen columns to pad
		values < 0 indicate screen columns to trim
		"""
		shards = self.shards
		if left < 0 or right < 0:
			trim_left = max(0, -left)
			cols = self.cols() - trim_left - max(0, -right)
			shards = shards_trim_sides(shards, trim_left, cols)

		rows = self.rows()
		if left > 0 or right > 0:
			top_rows, top_cviews = shards[0]
			if left > 0:
				new_top_cviews = (
					[(0,0,left,rows,None,blank_canvas)] +
					top_cviews)
			else:
				new_top_cviews = top_cviews[:] #copy

			if right > 0:
				new_top_cviews.append(
					(0,0,right,rows,None,blank_canvas))
			shards = [(top_rows, new_top_cviews)] + shards[1:]

		self.translate_coords(left, 0)
		self.shards = shards


	def pad_trim_top_bottom(self, top, bottom):
		"""
		Pad or trim this canvas on the top and bottom.
		"""
		orig_shards = self.shards

		if top < 0 or bottom < 0:
			trim_top = max(0, -top)
			rows = self.rows() - trim_top - max(0, -bottom)
			self.trim(trim_top, rows)

		cols = self.cols()
		if top > 0:
			self.shards = [(top,
				[(0,0,cols,top,None,blank_canvas)])] + \
				self.shards
			self.translate_coords(0, top)
		
		if bottom > 0:
			if orig_shards is self.shards:
				self.shards = self.shards[:]
			self.shards.append((bottom,
				[(0,0,cols,bottom,None,blank_canvas)]))

		
	def overlay(self, other, left, right, top, bottom ):
		"""Overlay other onto this canvas."""
		
		width = self.cols()-left-right
		height = self.rows()-top-bottom
		
		assert other.rows() == height, "top canvas of overlay not the size expected!" + `other.rows(),top,bottom,height`
		assert other.cols() == width, "top canvas of overlay not the size expected!" + `other.cols(),left,right,width`

		shards = self.shards
		top_shards = []
		side_shards = self.shards
		bottom_shards = []
		if top:
			side_shards = shards_trim_top(shards, top)
			top_shards = shards_trim_rows(shards, top)
		if bottom:
			bottom_shards = shards_trim_top(side_shards, height)
			side_shards = shards_trim_rows(side_shards, height)

		left_shards = []
		right_shards = []
		if left:
			left_shards = [shards_trim_sides(side_shards, 0, left)]
		if right:
			right_shards = [shards_trim_sides(side_shards, 
				left + width, right)]
		
		if left or right:
			middle_shards = shards_join(left_shards + 
				[other.shards] + right_shards)
		else:
			middle_shards = other.shards

		self.shards = top_shards + middle_shards + bottom_shards
		
		self.cursor = other.cursor
		self.translate_coords( left, top )


	def fill_attr(self, a):
		"""
		Apply attribute a to all areas of this canvas with default
		attribute currently set to None, leaving other attributes
		intact."""
		
		for num_rows, cviews in self.shards:
			for i in range(len(cviews)):
				cv = cviews[i]
				if cv[4] is None:
					cviews[i] = cv[:4] + (a,) + cv[5:]


	def translate_coords(self,dx,dy):
		"""
		Shift cursor coords by (dx, dy).
		"""
		if self.cursor:
			x, y = self.cursor
			self.cursor =  x+dx, y+dy


def shard_body_row(sbody):
	"""
	Return one row, advancing the iterators in sbody.

	** MODIFIES sbody by calling next() on its iterators **
	"""
	row = []
	for done_rows, content_iter, cview in sbody:
		if content_iter:
			row.extend(content_iter.next())
		else:
			# need to skip this unchanged canvas
			if row and type(row[-1]) == type(0):
				row[-1] = row[-1] + cview[2]
			else:
				row.append(cview[2])

	return row


def shard_body_tail(num_rows, sbody):
	"""
	Return a new shard tail that follows this shard body.
	"""
	shard_tail = []
	col_gap = 0
	done_rows = 0
	for done_rows, content_iter, cview in sbody:
		cols, rows = cview[2:4]
		done_rows += num_rows
		if done_rows == rows:
			col_gap += cols
			continue
		shard_tail.append((col_gap, done_rows, content_iter, cview))
		col_gap = 0
	return shard_tail


def shards_delta(shards, other_shards):
	"""
	Yield shards1 with cviews that are the same as shards2 
	having canv = None.
	"""
	other_shards_iter = iter(other_shards)
	other_num_rows = other_cviews = None
	done = other_done = 0
	for num_rows, cviews in shards:
		if other_num_rows is None:
			other_num_rows, other_cviews = other_shards_iter.next()
		while other_done < done:
			other_done += other_num_rows
			other_num_rows, other_cviews = other_shards_iter.next()
		if other_done > done:
			yield (num_rows, cviews)
			done += num_rows
			continue
		# top-aligned shards, compare each cview
		yield (num_rows, shard_cviews_delta(cviews, other_cviews))
		other_done += other_num_rows
		other_num_rows = None
		done += num_rows

def shard_cviews_delta(cviews, other_cviews):
	"""
	"""
	other_cviews_iter = iter(other_cviews)
	other_cv = None
	cols = other_cols = 0
	for cv in cviews:
		if other_cv is None:
			other_cv = other_cviews_iter.next()
		while other_cols < cols:
			other_cols += other_cv[2]
			other_cv = other_cviews_iter.next()
		if other_cols > cols:
			yield cv
			cols += cv[2]
			continue
		# top-left-aligned cviews, compare them
		if cv[5] is other_cv[5] and cv[:5] == other_cv[:5]:
			yield cv[:5]+(None,)+cv[6:]
		else:
			yield cv
		other_cols += other_cv[2]
		other_cv = None
		cols += cv[2]



def shard_body(cviews, shard_tail, create_iter=True, iter_default=None):
	"""
	Return a list of (done_rows, content_iter, cview) tuples for 
	this shard and shard tail.

	If a canvas in cviews is None (eg. when unchanged from 
	shard_cviews_delta()) or if create_iter is False then no 
	iterator is created for content_iter.

	iter_default is the value used for content_iter when no iterator
	is created.
	"""
	col = 0
	body = [] # build the next shard tail
	cviews_iter = iter(cviews)
	for col_gap, done_rows, content_iter, tail_cview in shard_tail:
		while col_gap:
			cview = cviews_iter.next()
			(trim_left, trim_top, cols, rows, def_attr, canv) = \
				cview[:6]
			col += cols
			col_gap -= cols
			if create_iter and canv:
				new_iter = canv.content(trim_left, trim_top, 
					cols, rows, def_attr)
			else:
				new_iter = iter_default
			body.append((0, new_iter, cview))
		body.append((done_rows, content_iter, tail_cview))
	for cview in cviews_iter:
		(trim_left, trim_top, cols, rows, def_attr, canv) = \
			cview[:6]
		if create_iter and canv:
			new_iter = canv.content(trim_left, trim_top, cols, rows, 
				def_attr)
		else:
			new_iter = iter_default
		body.append((0, new_iter, cview))
	return body


def shards_trim_top(shards, top):
	"""
	Return shards with top rows removed.
	"""
	assert top > 0

	shard_iter = iter(shards)
	shard_tail = []
	# skip over shards that are completely removed
	for num_rows, cviews in shard_iter:
		if top < num_rows:
			break
		sbody = shard_body(cviews, shard_tail, False)
		shard_tail = shard_body_tail(num_rows, sbody)
		top -= num_rows
	else:
		raise CanvasError("tried to trim shards out of existance")
	
	sbody = shard_body(cviews, shard_tail, False)
	shard_tail = shard_body_tail(num_rows, sbody)
	# trim the top of this shard
	new_sbody = []
	for done_rows, content_iter, cv in sbody:
		new_sbody.append((0, content_iter, 
			cview_trim_top(cv, done_rows+top)))
	sbody = new_sbody
	
	new_shards = [(num_rows-top, 
		[cv for done_rows, content_iter, cv in sbody])]
	
	# write out the rest of the shards
	new_shards.extend(shard_iter)

	return new_shards

def shards_trim_rows(shards, keep_rows):
	"""
	Return the topmost keep_rows rows from shards.
	"""
	assert keep_rows > 0

	shard_tail = []
	new_shards = []
	done_rows = 0
	for num_rows, cviews in shards:
		if done_rows >= keep_rows:
			break
		new_cviews = []
		for cv in cviews:
			if cv[3] + done_rows > keep_rows:
				new_cviews.append(cview_trim_rows(cv, 
					keep_rows - done_rows))
			else:
				new_cviews.append(cv)

		if num_rows + done_rows > keep_rows:
			new_shards.append((keep_rows - done_rows, new_cviews))
		else:
			new_shards.append((num_rows, new_cviews))
		done_rows += num_rows

	return new_shards

def shards_trim_sides(shards, left, cols):
	"""
	Return shards with starting from column left and cols total width.
	"""
	assert left >= 0 and cols > 0
	shard_tail = []
	new_shards = []
	right = left + cols
	for num_rows, cviews in shards:
		sbody = shard_body(cviews, shard_tail, False)
		shard_tail = shard_body_tail(num_rows, sbody)
		new_cviews = []
		col = 0
		for done_rows, content_iter, cv in sbody:
			cv_cols = cv[2]
			next_col = col + cv_cols
			if done_rows or next_col <= left or col >= right:
				col = next_col
				continue
			if col < left:
				cv = cview_trim_left(cv, left - col)
				col = left
			if next_col > right:
				cv = cview_trim_cols(cv, right - col)
			new_cviews.append(cv)
			col = next_col
		if not new_cviews:
			prev_num_rows, prev_cviews = new_shards[-1]
			new_shards[-1] = (prev_num_rows+num_rows, prev_cviews)
		else:
			new_shards.append((num_rows, new_cviews))
	return new_shards

def shards_join(shard_lists):
	"""
	Return the result of joining shard lists horizontally.
	All shards lists must have the same number of rows.
	"""
	shards_iters = [iter(sl) for sl in shard_lists]
	shards_current = [i.next() for i in shards_iters]

	new_shards = []
	while True:
		new_cviews = []
		num_rows = min([r for r,cv in shards_current])

		shards_next = []
		for rows, cviews in shards_current:
			if cviews:
				new_cviews.extend(cviews)
			shards_next.append((rows - num_rows, None))

		shards_current = shards_next
		new_shards.append((num_rows, new_cviews))

		# advance to next shards
		try:
			for i in range(len(shards_current)):
				if shards_current[i][0] > 0:
					continue
				shards_current[i] = shards_iters[i].next()
		except StopIteration:
			break
	return new_shards


def cview_trim_rows(cv, rows):
	return cv[:3] + (rows,) + cv[4:]
	
def cview_trim_top(cv, trim):
	return (cv[0], trim + cv[1], cv[2], cv[3] - trim) + cv[4:]

def cview_trim_left(cv, trim):
	return (cv[0] + trim, cv[1], cv[2] - trim,) + cv[3:]

def cview_trim_cols(cv, cols):
	return cv[:2] + (cols,) + cv[3:]


		

def CanvasCombine(l):
	"""Stack canvases in l vertically and return resulting canvas."""
	clist = [CompositeCanvas(c) for c in l]

	shards = []
	row = 0
	cursor = None
	for canv in clist:
		shards.extend(canv.shards)
		canv_cursor = canv.cursor
		if canv_cursor:
			x, y = canv_cursor
			cursor = (x, y+row)
		row += canv.rows()
	
	combined_canvas = CompositeCanvas()
	combined_canvas.shards = shards
	combined_canvas.cursor = cursor
	return combined_canvas


def CanvasJoin(l):
	"""Join canvases in l horizontally. Return result.

	l -- [canvas1, colnum2, canvas2, ... ,colnumN, canvasN]
		colnumX is the screen column count between the start of
		canvas(X-1) and canvasX, colnumX >= canvas(X-1).cols()
	"""
	
	# make silly parameter slightly less silly
	l = [0] + l
	l2 = [( l[i], l[i+1].rows(), l[i+1] ) for i in range(0,len(l),2)]

	maxrow = max([rows for col_diff, rows, canv in l2])

	shard_lists = []
	joined_canvas = CompositeCanvas()
	col = prev_col = 0
	for col_diff, rows, canv in l2:
		canv = CompositeCanvas(canv)
		if col_diff > col-prev_col:
			canv.pad_trim_left_right(col_diff - (col-prev_col), 0)
			prev_col = col + (col_diff - (col-prev_col))
		else:
			prev_col = col
		if rows < maxrow:
			canv.pad_trim_top_bottom(0, maxrow - rows)
		if canv.cursor:
			joined_canvas.cursor = canv.cursor
			joined_canvas.translate_coords(col, 0)
		shard_lists.append(canv.shards)
		col += canv.cols()
	joined_canvas.shards = shards_join(shard_lists)
	return joined_canvas


def apply_text_layout( text, attr, ls, maxcol ):
	utext = type(text)==type(u"")
	t = []
	a = []
	c = []
	
	class AttrWalk:
		pass
	aw = AttrWalk
	aw.k = 0 # counter for moving through elements of a
	aw.off = 0 # current offset into text of attr[ak]
	
	def arange( start_offs, end_offs ):
		"""Return an attribute list for the range of text specified."""
		if start_offs < aw.off:
			aw.k = 0
			aw.off = 0
		o = []
		while aw.off < end_offs:
			if len(attr)<=aw.k:
				# run out of attributes
				o.append((None,end_offs-max(start_offs,aw.off)))
				break
			at,run = attr[aw.k]
			if aw.off+run <= start_offs:
				# move forward through attr to find start_offs
				aw.k += 1
				aw.off += run
				continue
			if end_offs <= aw.off+run:
				o.append((at, end_offs-max(start_offs,aw.off)))
				break
			o.append((at, aw.off+run-max(start_offs, aw.off)))
			aw.k += 1
			aw.off += run
		return o

	
	for line_layout in ls:
		# trim the line to fit within maxcol
		line_layout = trim_line( line_layout, text, 0, maxcol )
		
		line = []
		linea = []
		linec = []
			
		def attrrange( start_offs, end_offs, destw ):
			"""
			Add attributes based on attributes between
			start_offs and end_offs. 
			"""
			if start_offs == end_offs:
				[(at,run)] = arange(start_offs,end_offs)
				rle_append_modify( linea, ( at, destw ))
				return
			if destw == end_offs-start_offs:
				for at, run in arange(start_offs,end_offs):
					rle_append_modify( linea, ( at, run ))
				return
			# encoded version has different width
			o = start_offs
			for at, run in arange(start_offs, end_offs):
				if o+run == end_offs:
					rle_append_modify( linea, ( at, destw ))
					return
				tseg = text[o:o+run]
				tseg, cs = apply_target_encoding( tseg )
				segw = rle_len(cs)
				
				rle_append_modify( linea, ( at, segw ))
				o += run
				destw -= segw
			
			
		for seg in line_layout:
			#if seg is None: assert 0, ls
			s = LayoutSegment(seg)
			if s.end:
				tseg, cs = apply_target_encoding(
					text[s.offs:s.end])
				line.append(tseg)
				attrrange(s.offs, s.end, rle_len(cs))
				rle_join_modify( linec, cs )
			elif s.text:
				tseg, cs = apply_target_encoding( s.text )
				line.append(tseg)
				attrrange( s.offs, s.offs, len(tseg) )
				rle_join_modify( linec, cs )
			elif s.offs:
				if s.sc:
					line.append(" "*s.sc)
					attrrange( s.offs, s.offs, s.sc )
			else:
				line.append(" "*s.sc)
				linea.append((None, s.sc))
				linec.append((None, s.sc))
			
		t.append("".join(line))
		a.append(linea)
		c.append(linec)
		
	return Canvas(t,a,c, maxcol=maxcol)



