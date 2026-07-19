import math

import app
from events.input import Buttons, BUTTON_TYPES


class Circles(app.App):
    """Draw three concentric circles on the Tildagon display."""

    # (radius, (r, g, b)) for each ring, outermost last.
    RINGS = (
        (40, (1.0, 0.2, 0.2)),
        (70, (0.2, 1.0, 0.2)),
        (100, (0.2, 0.4, 1.0)),
    )

    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)

    def update(self, delta):
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.minimise()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0.0, 0.0, 0.0).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 4
        for radius, (r, g, b) in self.RINGS:
            ctx.rgb(r, g, b).arc(0, 0, radius, 0, 2 * math.pi, False).stroke()
        ctx.restore()
