#!/usr/bin/env python3
# For each menu, calcualte all of its descendant symbols and choices.

import sys, os.path, subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import kconfiglib

class KernelVersion(object):
    """Lazy evaluation of kernel version finder."""
    def __str__(self):
        return subprocess.check_output(
            ["make", "kernelversion"],
            universal_newlines=True).strip()

for k, v in {
    'ARCH': "x86_64",
    'SRCARCH': "x86",
    'KERNELVERSION': KernelVersion(),
}.items():
    if not k in os.environ:
        os.environ[k] = str(v)

class Tree(object):
    def __init__(self, parent, items):
        self.parent = parent
        self.items = items
    def handle_items(self):
        for item in self.items:
            if item.is_symbol():
                self.handle_symbol(item)
            elif item.is_menu():
                self.handle_menu(item)
            elif item.is_choice():
                self.handle_choice(item)
            elif item.is_comment():
                self.handle_comment(item)

    def handle_symbol(self, item):
        pass
    def make_subtree(self, item):
        tree = self.__class__(item, item.get_items())
        return tree
    def handle_menu(self, item):
        tree = self.make_subtree(item)
        tree.handle_items()
        return tree
    def handle_choice(self, item):
        tree = self.make_subtree(item)
        tree.handle_items()
        return tree
    def handle_comment(self, item):
        pass

class CountingTree(Tree):
    """
    An extension of Tree which counts the available children.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.count = 0
        self.selected_count = 0
        # Global offset, relative to first tree item.
        self.offset = 0
        self.selected_offset = 0
    def make_subtree(self, item):
        tree = self.__class__(item, item.get_items())
        tree.offset = self.offset + self.count
        tree.selected_offset = self.selected_offset + self.selected_count
        return tree
    def handle_symbol(self, item):
        super().handle_symbol(item)
        # Choices have only one possible value, handle it at the Choice.
        if not item.is_choice_symbol():
            self.count += 1
        # bools, tri-states (incl. choices) affect code generation, track those.
        if item.get_value() in 'ym':
            self.selected_count += 1
    def handle_menu(self, item):
        menu = super().handle_menu(item)
        self.count += menu.count
        self.selected_count += menu.selected_count
        return menu
    def handle_choice(self, item):
        choice = super().handle_choice(item)
        # Treat a choice as a single item, the user must pick one
        choice.count += 1
        self.count += choice.count
        self.selected_count += choice.selected_count
        return choice

import html
class HtmlTree(CountingTree):
    def __init__(self, *args):
        super().__init__(*args)
        self.html = ''

    def _write_html(self, html):
        self.html += html
    def _write_text(self, text):
        self._write_html(html.escape(text))
    def _write_attr(self, name, value):
        self._write_html(' %s=%s' % (name, html.escape(value)))

    def _wrap_tag(tag_name):
        def decorator(func):
            def wrapped_fn(self, *args):
                self._write_html('<%s>' % tag_name)
                func(self, *args)
                self._write_html('</%s>\n' % tag_name)
            return wrapped_fn
        return decorator

    @_wrap_tag('ul')
    def handle_items(self):
        super().handle_items()

    def _write_counter(self):
        sc, c = self.selected_count, self.count
        sc += self.selected_offset
        c += self.offset
        self._write_text('%d/%d ' % (sc, c))

    @_wrap_tag('li')
    def handle_symbol(self, item):
        # ( ) Symbol (if parent is choice)
        # [ ] Symbol (if parent is not choice)
        tree = super().handle_symbol(item)
        self._write_counter()
        # Disable since it is just for reading
        name = 'CONFIG_%s' % item.get_name()
        self._write_html('<input disabled id="%s" class="symbol"' % name)
        val = item.get_value()
        if item.is_choice_symbol():
            choice_name = 'choice-%s' % id(item.get_parent())
            self._write_html(' type="radio" name="%s"' % choice_name)
            if item.is_choice_selection():
                self._write_html(' checked')
        else:
            if item.get_type() in (kconfiglib.BOOL, kconfiglib.TRISTATE):
                self._write_html(' type="checkbox"')
                if val in 'ym':
                    self._write_html(' checked')
            else:
                self._write_attr('value', val)
        self._write_html('><label for="%s">' % name)
        self._write_text(item.get_name())
        self._write_html('</label>')

    def _write_menu_tree(self, item, tree, name):
        assert ' ' not in name
        if item.is_menu():
            className = 'menu'
            text = item.get_title()
        else:
            className = 'choice'
            text = item.get_prompts()[0]
        self._write_html('<input type="checkbox" id="%s" class="%s" ' % \
                (name, className))
        if item.is_menu() and tree.selected_count > 0:
            self._write_html(' checked')
        self._write_html('><label for="%s">' % name)
        self._write_text('%s [%d/%d]' % (text, tree.selected_count, tree.count))
        self._write_html('</label>\n')
        self._write_html(tree.html)

    @_wrap_tag('li')
    def handle_menu(self, item):
        # Title
        tree = super().handle_menu(item)
        name = 'menu-%s:%d' % item.get_location()
        self._write_menu_tree(item, tree, name)
        return tree

    @_wrap_tag('li')
    def handle_choice(self, item):
        # ...
        tree = super().handle_choice(item)
        name = 'choice-%s' % id(item)
        self._write_counter()
        self._write_menu_tree(item, tree, name)
        return tree

    @_wrap_tag('li')
    def handle_comment(self, item):
        # *** Comment ***
        tree = super().handle_comment(item)
        self._write_text(item.get_text())

def main():
    cache_file = '/tmp/picked-kconfig'
    import pickle
    try:
        conf = pickle.load(open(cache_file, 'rb'))
    except:
        sys.setrecursionlimit(100000)
        conf = kconfiglib.Config()
        pickle.dump(conf, open(cache_file, 'wb'))

    if len(sys.argv) >= 2:
        conf.load_config(sys.argv[1])

    #tree = CountingTree(None, conf.get_top_level_items())
    tree = HtmlTree(None, conf.get_top_level_items())
    tree.handle_items()
    print('''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="generator" content="https://github.com/Lekensteyn/Kconfiglib/blob/hackery/examples/count_children.py">
<title>Kernel configuration for ''' + os.environ['KERNELVERSION'] + '''</title>
<style>
.choice + label {
    background: #ccf;
}
.menu + label {
    background: #ffc;
}
.symbol:checked + label {
    font-weight: bold;
}
.choice:not(:checked) ~ ul,
.menu:not(:checked) ~ ul {
    display: none;
}
.menu:target ~ ul {
    background: #fcc;
}
#toolbox {
    position: fixed;
    right: 0;
    padding: 3px;
    top: 0;
    text-align: center;
}
#menuNav {
    text-align: left;
    height: 90vh;
    overflow: auto;
}
</style>
</head>
<body>
''')
    print('%d items<br>\n' % tree.count)
    print(tree.html)
    print(r'''

<div id="toolbox">
<button onclick="expandMenu(true)">Expand all menus</button>
<button onclick="expandMenu(false)">Collapse all menus</button>
<br>
<label><input type="checkbox" onclick="hideDisabled(this.checked)">
Hide disabled options</label>
<br>
Sort:
<label><input type="radio" name="menuSort" value="menuId"> Name</label>
<label><input type="radio" name="menuSort" value="selectedCount"> Sel</label>
<label><input type="radio" name="menuSort" value="count"> Cnt</label>
<ul id="menuNav">
</ul>
</div>

<script>
var menus = [].slice.call(document.querySelectorAll(".menu"));
function expandMenu(expanded) {
    menus.forEach(function(menu) {
        menu.checked = expanded;
    });
}
function hideDisabled(hide) {
    [].forEach.call(document.querySelectorAll(".symbol:not(:checked)"),
        hide ? function(el) {
            el.parentNode.style.display = "none";
        } : function(el) {
            delete el.parentNode.style.display;
        });
}

var menuNav = document.getElementById("menuNav")
menus.forEach(function(menu) {
    // 1: label, 2: selectedCount, 3: count
    var label = menu.nextElementSibling;
    var itemInfo = label.textContent.match(/^\s*(.*) \[(\d+)\/(\d+)\]\s*$/);

    var li = document.createElement("li");
    li.dataset.menuId = menu.id;
    li.dataset.selectedCount = +itemInfo[2];
    li.dataset.count = +itemInfo[3];
    var a = document.createElement("a");
    a.href = menuNav.href = "#" + encodeURIComponent(menu.id);
    // assume label following checkbox
    a.textContent = itemInfo[0];
    a.onclick = handleNav;
    li.appendChild(a);
    menuNav.appendChild(li);

    // replace <label>...</label> by <label><a>...</a></label>
    var menu_link = document.createElement("a");
    menu_link.href = a.href;
    menu_link.appendChild(label.firstChild);
    label.appendChild(menu_link);

    // TODO this breaks label for checkbox, add new anchor "#" after element
    var parentMenu = findParentMenu(menu);
    if (parentMenu) {
        var goUp = document.createElement("a");
        goUp.href = "#" + encodeURIComponent(parentMenu.dataset.menuId);
        goUp.textContent = parentMenu.nextElementSibling.textContent;
        menu.parentNode.insertBefore(goUp, menu.parentNode.querySelector("ul"));
    }
});
function findParentMenu(el) {
    el = el.parentNode; /* input -> li */
    if (el) el = el.parentNode; /* li -> ul */
    while (el) {
        if (el.classList.contains("menu")) {
            return el;
        }
        el = el.previousElementSibling;
    }
    return null;
}
// TODO move to hashchangeevent
function handleNav() {
    'use strict';
    // expand parent tree items
    var inp = document.getElementById(this.parentNode.dataset.menuId);
    while ((inp = findParentMenu(inp))) {
        inp.checked = true;
    }
}

function sortChildren(element, compareFunc, reverse) {
    var nodes = [].slice.call(menuNav.children);
    nodes.sort(compareFunc);
    if (reverse) {
        nodes.reverse();
    }
    nodes.forEach(function(child) {
        element.appendChild(child);
    });
}
function sortMenu() {
    'use strict';
    var key = this.value;
    if (key === 'menuId') {
        sortChildren(menuNav, function(a, b) {
            return a.dataset[key].localeCompare(b.dataset[key]);
        });
    } else {
        sortChildren(menuNav, function(a, b) {
            return a.dataset[key] - b.dataset[key];
        }, true);
    }
}
[].forEach.call(document.getElementsByName("menuSort"), function(c) {
    c.onclick = sortMenu;
});
</script>
</body>
</html>
''')

if __name__ == '__main__':
    main()
