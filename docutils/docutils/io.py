# Author: David Goodger
# Contact: goodger@users.sourceforge.net
# Revision: $Revision$
# Date: $Date$
# Copyright: This module has been placed in the public domain.

"""
I/O classes provide a uniform API for low-level input and output.  Subclasses
will exist for a variety of input/output mechanisms.
"""

__docformat__ = 'reStructuredText'

import sys
import locale


class Input:

    """
    Abstract base class for input wrappers.
    """

    default_source_path = None

    def __init__(self, options, source=None, source_path=None):
        self.options = options
        """An option values object with "input_encoding" and "output_encoding"
        attributes (typically a `docutils.optik.Values` object)."""

        self.source = source
        """The source of input data."""

        self.source_path = source_path
        """A text reference to the source."""

        if not source_path:
            self.source_path = self.default_source_path

    def __repr__(self):
        return '%s: source=%r, source_path=%r' % (self.__class__, self.source,
                                                  self.source_path)

    def read(self, reader):
        raise NotImplementedError

    def decode(self, data):
        """
        Decode a string, `data`, heuristically.
        Raise UnicodeError if unsuccessful.

        The client application should call ``locale.setlocale`` at the
        beginning of processing::

            locale.setlocale(locale.LC_ALL, '')
        """
        encodings = [self.options.input_encoding, 'utf-8']
        try:
            encodings.append(locale.nl_langinfo(locale.CODESET))
        except:
            pass
        try:
            encodings.append(locale.getlocale()[1])
        except:
            pass
        try:
            encodings.append(locale.getdefaultlocale()[1])
        except:
            pass
        encodings.append('latin-1')
        for enc in encodings:
            if not enc:
                continue
            try:
                decoded = unicode(data, enc)
                return decoded
            except (UnicodeError, LookupError):
                pass
        raise UnicodeError(
            'Unable to decode input data.  Tried the following encodings: %s.'
            % ', '.join([repr(enc) for enc in encodings if enc]))


class Output:

    """
    Abstract base class for output wrappers.
    """

    default_destination_path = None

    def __init__(self, options, destination=None, destination_path=None):
        self.options = options
        """An option values object with "input_encoding" and "output_encoding"
        attributes (typically a `docutils.optik.Values` object)."""

        self.destination = destination
        """The destination for output data."""

        self.destination_path = destination_path
        """A text reference to the destination."""

        if not destination_path:
            self.destination_path = self.default_destination_path

    def __repr__(self):
        return ('%s: destination=%r, destination_path=%r'
                % (self.__class__, self.destination, self.destination_path))

    def write(self, data):
        raise NotImplementedError


class FileInput(Input):

    """
    Input for single, simple file-like objects.
    """

    def __init__(self, options, source=None, source_path=None, autoclose=1):
        """
        :Parameters:
            - `source`: either a file-like object (which is read directly), or
              `None` (which implies `sys.stdin` if no `source_path` given).
            - `source_path`: a path to a file, which is opened and then read.
            - `autoclose`: close automatically after read (boolean); always
              false if `sys.stdin` is the source.
        """
        Input.__init__(self, options, source, source_path)
        self.autoclose = autoclose
        if source is None:
            if source_path:
                self.source = open(source_path)
            else:
                self.source = sys.stdin
                self.autoclose = None
        if not source_path:
            try:
                self.source_path = self.source.name
            except AttributeError:
                pass

    def read(self, reader):
        """Read and decode a single file and return the data."""
        data = self.source.read()
        if self.autoclose:
            self.close()
        return self.decode(data)

    def close(self):
        self.source.close()


class FileOutput(Output):

    """
    Output for single, simple file-like objects.
    """

    def __init__(self, options, destination=None, destination_path=None,
                 autoclose=1):
        """
        :Parameters:
            - `destination`: either a file-like object (which is written
              directly) or `None` (which implies `sys.stdout` if no
              `destination_path` given).
            - `destination_path`: a path to a file, which is opened and then
              written.
            - `autoclose`: close automatically after write (boolean); always
              false if `sys.stdout` is the destination.
        """
        Output.__init__(self, options, destination, destination_path)
        self.opened = 1
        self.autoclose = autoclose
        if destination is None:
            if destination_path:
                self.opened = None
            else:
                self.destination = sys.stdout
                self.autoclose = None
        if not destination_path:
            try:
                self.destination_path = self.destination.name
            except AttributeError:
                pass

    def open(self):
        self.destination = open(self.destination_path, 'w')
        self.opened = 1

    def write(self, data):
        """Encode `data`, write it to a single file, and return it."""
        output = data.encode(self.options.output_encoding)
        if not self.opened:
            self.open()
        self.destination.write(output)
        if self.autoclose:
            self.close()
        return output

    def close(self):
        self.destination.close()
        self.opened = None


class StringInput(Input):

    """
    Direct string input.
    """

    default_source_path = 'string input'

    def read(self, reader):
        """Decode and return the source string."""
        if self.options.input_encoding is None:
            return self.source
        else:
            return self.decode(self.source)


class StringOutput(Output):

    """
    Direct string output.
    """

    default_destination_path = 'string output'

    def write(self, data):
        """Encode `data`, store it in `self.destination`, and return it."""
        if self.options.output_encoding is None:
            self.destination = data
        else:
            self.destination = data.encode(self.options.output_encoding)
        return self.destination


class NullInput(Input):

    """
    Degenerate input: read nothing.
    """

    default_source_path = 'null input'

    def read(self, reader):
        """Return a null string."""
        return u''


class NullOutput(Output):

    """
    Degenerate output: write nothing.
    """

    default_destination_path = 'null output'

    def write(self, data):
        """Do nothing ([don't even] send data to the bit bucket)."""
        pass
