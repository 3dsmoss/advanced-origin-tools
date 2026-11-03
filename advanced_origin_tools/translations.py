import bpy

from .operators import I18N_CTX

# Short interface words. Registered ONLY in the add-on's own context: Blender's own
# catalogs translate words such as "Back" or "Space" with other meanings, and
# registering them globally would also change Blender's own interface.
TR_UI = {
    "Origin Tools": "Origin Araçları",
    "Origin": "Origin",
    "Options": "Seçenekler",
    "Selection Center": "Seçim Merkezi",
    "Bounding Box": "Sınır Kutusu",
    "Shortcut: %s": "Kısayol: %s",
    "Pie menu: %s": "Pie menü: %s",
    "Transform menus: %s": "Dönüşüm menüleri: %s",
    "Transform Menu": "Dönüşüm Menüsü",
    "Set origin from selection or bounds": "Seçimden ya da sınır kutusundan origin",
    "Anchor": "Nokta",
    "World Origin": "Dünya Merkezi",
    "Pie menu": "Pie menü",
    "Transform menus": "Dönüşüm menüleri",
    "Set": "Seç",
    "Add snap element": "Snap hedefi ekle",
    "Close": "Kapat",
    "Origins from selection or bounds": "Seçimden ya da sınır kutusundan origin",
    "Card Style Sidebar": "Kart Görünümlü Kenar Çubuğu",
    "Shared tab: classic panel": "Ortak sekme: klasik panel",
    "Depth: %s": "Derinlik: %s",
    "Shortcuts": "Kısayollar",
    "Sidebar Tab": "Kenar Çubuğu Sekmesi",
    "Origin to Selection": "Origin'i Seçime Taşı",
    "Origin to Bounding Box": "Origin'i Sınır Kutusuna Taşı",
    "Center": "Merkez",
    "Depth": "Derinlik",
    "Multiple Objects": "Çoklu Obje",
    "Space": "Eksen",
    "Bounds Space": "Kutu Ekseni",
    "Measure": "Ölçüm",
    "Then": "Ardından",
    "Edit Mode Selection": "Edit Mode Seçimi",
    "Left": "Sol",
    "Right": "Sağ",
    "Front": "Ön",
    "Middle": "Orta",
    "Back": "Arka",
    "Bottom": "Alt",
    "Top": "Üst",
    "Top Left": "Sol Üst",
    "Top Right": "Sağ Üst",
    "Bottom Left": "Sol Alt",
    "Bottom Right": "Sağ Alt",
    "Each Object": "Her Obje Ayrı",
    "Combined": "Ortak",
    "Local": "Yerel",
    "World": "Dünya",
    "With Modifiers": "Modifier'lar Dahil",
    "Base Mesh": "Ham Mesh",
    "Median": "Medyan",
    "Bounds": "Kutu",
    "Active": "Aktif",
    "Keep Position": "Yerinde Kalsın",
    "Drop to Floor": "Yere Oturt",
    "To World Origin": "Dünya Merkezine",
    "Keep Mirror Plane": "Ayna Düzlemini Koru",
    "Orientation": "Yönelim",
    "Orient Origin": "Eksenleri Hizala",
    "Align To": "Hizala",
    "Main Axis": "Ana Eksen",
    "Auto": "Otomatik",
    "Shape": "Şekil",
    "Selection": "Seçim",
    "View": "Görünüm",
    "3D Cursor": "3D İmleç",
    "Nearest": "En Yakın",
    "Long Side": "Uzun Kenar",
    "Ctrl Q Does Not Quit": "Ctrl Q Çıkış Yapmaz",
    "Turn 90°": "90° çevir",
    "from the selection": "seçimden",
    "from the shape": "şekilden",
    "Mode: %s": "Mod: %s",
    "Apply": "Uygula",
    "Cancel": "Vazgeç",
    "Quarter Turns": "Çeyrek Dönüşler",
    "Any": "Fark Etmez",
    "Export": "Dışa Aktarım",
    "Fix": "Düzelt",
    "Fix for Export": "Dışa Aktarım İçin Düzelt",
    "Ready for export": "Dışa aktarıma hazır",
    "Scale not applied": "Ölçek uygulanmamış",
    "Negative scale": "Negatif ölçek",
    "Origin far from the mesh": "Origin mesh'ten uzak",
    "Apply Scale": "Ölçeği Uygula",
    "Origin to Bottom Center": "Origin'i Alt Ortaya",
    "Uses the selected faces": "Seçili yüzlere göre",
    "Uses the flat faces": "Düz yüzlere göre",
    "Copies the active object": "Aktif objeden kopyalar",
    "Straight to world axes": "Dünya eksenlerine düzeltir",
    "Select the others, then the one to copy": "Önce diğerleri, en son kaynak",
    "Select objects to check them for export": "Kontrol için nesne seç",
}

# Full sentences (tooltips, reports, poll messages). They are unique to this add-on,
# so they are also registered in the default contexts that tooltips and reports use.
TR_TEXT = {
    "Move the origin to the selected vertices, edges or faces (works in Object Mode too, "
    "using the stored Edit Mode selection)":
        "Origin'i seçili vertex, edge veya face'lere taşır (Object Mode'da da çalışır, "
        "Edit Mode'daki son seçimi kullanır)",
    "Move the origin to a point of the bounding box": "Origin'i sınır kutusunun bir noktasına taşır",
    "Name of the sidebar (N panel) tab that shows the tools":
        "Araçların görüneceği kenar çubuğu (N paneli) sekmesinin adı",
    "Which side along Y the grid buttons use": "Grid düğmelerinin Y ekseninde hangi tarafı kullanacağı",
    "Axes used when the center is the bounds of the selection": "Merkez \"Kutu\" iken kullanılan eksenler",
    "In Edit Mode, use only the selected vertices (the whole mesh when nothing is selected)":
        "Edit Mode'da yalnızca seçili vertex'leri kullan (hiçbir şey seçili değilse tüm mesh)",
    "Negative X side": "Eksi X tarafı",
    "Middle of the X range": "X aralığının ortası",
    "Positive X side": "Artı X tarafı",
    "Negative Y side (the side seen from the Front view)": "Eksi Y tarafı (Front görünümünden bakılan yüz)",
    "Middle of the Y range": "Y aralığının ortası",
    "Positive Y side": "Artı Y tarafı",
    "Negative Z side": "Eksi Z tarafı",
    "Middle of the Z range": "Z aralığının ortası",
    "Positive Z side": "Artı Z tarafı",
    "Every object gets its own origin from its own geometry": "Her obje origin'ini kendi geometrisinden alır",
    "All objects get the same origin, computed from all of them together":
        "Tüm objeler, hepsi birlikte hesaplanan aynı origin'i alır",
    "Use the object's own axes (follows rotation)": "Objenin kendi eksenleri (dönüşü takip eder)",
    "Use the world axes": "Dünya eksenleri",
    "Measure the final shape, including modifiers such as Mirror or Array":
        "Mirror, Array gibi modifier'lar dahil son şekli ölçer",
    "Measure the mesh without modifiers": "Mesh'i modifier'lar olmadan ölçer",
    "Average position of the selected vertices": "Seçili vertex'lerin ortalama konumu",
    "Center of the box around the selected vertices": "Seçili vertex'leri saran kutunun merkezi",
    "The last selected vertex, edge or face": "Son seçilen vertex, edge veya face",
    "Only move the origin": "Yalnızca origin taşınır",
    "Draw Origin Tools as a card in its own sidebar tab. Off, or when the tab is shared with other tools (Tool, Item, View), the classic panel is used":
        "Origin Araçları'nı kendi kenar çubuğu sekmesinde kart olarak çizer. Kapalıyken ya da sekme başka araçlarla ortaksa (Tool, Item, View) klasik panel kullanılır",
    "Transform Orientation, Pivot Point and Snapping around the cursor":
        "İmlecin çevresinde dönüşüm yönelimi, pivot noktası ve snapping",
    "Then move the object so its lowest point rests on Z = 0":
        "Ardından objeyi, en alçak noktası Z = 0'a oturacak şekilde taşır",
    "Objects with a Mirror modifier keep their origin on the mirror plane, so the mirrored result does not change":
        "Mirror modifier'lı objelerde origin ayna düzleminde kalır; aynalanmış şekil bozulmaz",
    "Origin kept on the mirror plane (Mirror modifier): %s": "Origin ayna düzleminde tutuldu (Mirror modifier): %s",
    "Location is driven by NLA strips or drivers and was not adjusted: %s":
        "Konum NLA şeridi veya driver ile sürülüyor, ayarlanamadı: %s",
    "Rotation or scale is animated, the motion now turns around the new origin: %s":
        "Dönüş veya ölçek animasyonlu, hareket artık yeni origin etrafında: %s",
    "Final shape changed, these modifiers depend on the origin: %s. Ctrl+Z undoes it":
        "Son şekil değişti, şu modifier'lar origin'e bağlı: %s. Ctrl+Z ile geri alabilirsin",
    "Then move the object so the new origin sits at the world origin":
        "Ardından objeyi, yeni origin dünya merkezine gelecek şekilde taşır",
    "Put the origin on the chosen point and drop the object to the floor (Z = 0)":
        "Origin'i seçilen noktaya koyar ve objeyi yere oturtur (Z = 0)",
    "Put the origin on the chosen point and move the object to the world origin":
        "Origin'i seçilen noktaya koyar ve objeyi dünya merkezine taşır",
    "Move the origin to this bounding box point: %s": "Origin'i sınır kutusunun bu noktasına taşır: %s",
    "Works in Object Mode and mesh Edit Mode": "Object Mode'da ve mesh Edit Mode'da çalışır",
    "Select a mesh object": "Bir mesh obje seçin",
    "Select a mesh, curve, surface, text or metaball object":
        "Bir mesh, curve, surface, text veya metaball obje seçin",
    "No suitable object to work on": "Üzerinde çalışılacak uygun obje yok",
    "Origin could not be placed exactly on: %s (shared mesh data, or a 2D curve / text keeps its Z)":
        "Origin şu objelerde tam yerine konamadı: %s (paylaşılan mesh verisi ya da Z'si sabit kalan "
        "2D curve / text)",
    "Origin set": "Origin ayarlandı",
    "Origin set on %d objects": "%d objede origin ayarlandı",
    "object moved": "obje taşındı",
    "%d objects moved": "%d obje taşındı",
    "No active element: select a vertex, edge or face last": "Aktif eleman yok: en son bir vertex, edge veya face seçin",
    "Skipped %d objects without an active element": "Aktif elemanı olmayan %d obje atlandı",
    "Nothing selected: select vertices, edges or faces in Edit Mode first":
        "Seçim yok: önce Edit Mode'da vertex, edge veya face seçin",
    "Skipped %d objects without a stored selection": "Kayıtlı seçimi olmayan %d obje atlandı",
    "The selected objects have no geometry": "Seçili objelerin geometrisi yok",
    "Skipped %d objects without geometry": "Geometrisi olmayan %d obje atlandı",
    "Turn the object's axes (the origin's rotation) to the geometry, another object or the world. "
    "The mesh stays where it is":
        "Objenin eksenlerini (origin'in dönüşünü) geometriye, başka bir objeye ya da dünyaya hizalar. "
        "Mesh yerinden oynamaz",
    "Fix this export problem on the selected objects that have it":
        "Bu dışa aktarım sorununu, seçili objelerden sorunu olanlarda düzeltir",
    "Edit Mode: the selected faces, edges or vertices. Object Mode: the object's own flat faces":
        "Edit Mode: seçili face, edge veya vertex'ler. Object Mode: objenin kendi düz yüzleri",
    "The object's own flat faces (or the way its shape spreads)":
        "Objenin kendi düz yüzleri (ya da şeklinin uzandığı yönler)",
    "The selected faces, edges or vertices (in Object Mode, the stored Edit Mode selection)":
        "Seçili face, edge veya vertex'ler (Object Mode'da Edit Mode'daki son seçim)",
    "The axes of the active object (select the others, then the active one last)":
        "Aktif objenin eksenleri (önce diğerlerini, en son aktif objeyi seç)",
    "The current view: X to the right, Y up, Z toward you": "Mevcut görünüm: X sağa, Y yukarı, Z sana doğru",
    "The rotation of the 3D cursor": "3D imlecin dönüşü",
    "The world axes: straightens the object's axes": "Dünya eksenleri: objenin eksenlerini düzeltir",
    "Lay the axes on the found directions the way closest to the current axes, so the rotation values stay small":
        "Eksenleri bulunan yönlere, mevcut eksenlere en yakın biçimde yerleştirir; dönüş değerleri küçük kalır",
    "The face normal (main direction) becomes the Z axis": "Yüz normali (ana yön) Z ekseni olur",
    "The face normal (main direction) becomes the Y axis": "Yüz normali (ana yön) Y ekseni olur",
    "The face normal (main direction) becomes the X axis": "Yüz normali (ana yön) X ekseni olur",
    "Which object axis follows the face normal (Auto, Shape and Selection)":
        "Yüz normalini objenin hangi ekseninin izleyeceği (Otomatik, Şekil ve Seçim)",
    "No preference: the turn closest to the current axes": "Tercih yok: mevcut eksenlere en yakın dönüş",
    "The longest side lies along X": "En uzun kenar X boyunca",
    "The longest side lies along Y": "En uzun kenar Y boyunca",
    "The longest side lies along Z": "En uzun kenar Z boyunca",
    "Which axis runs along the object's longest side (with Main Axis on Nearest). "
    "Settles it when a box turned past 45 degrees gets two axes swapped":
        "Objenin en uzun kenarı boyunca hangi eksenin uzanacağı (Ana Eksen \"En Yakın\" iken). "
        "45 dereceden fazla dönmüş bir kutuda iki eksen yer değiştirirse bunu düzeltir",
    "Move the scale into the mesh so the scale is 1 (also turns mirrored faces outward)":
        "Ölçeği mesh'e aktarır, ölçek 1 olur (aynalanmış yüzleri de dışa çevirir)",
    "Put the origin on the bottom center of the object's own box": "Origin'i objenin kendi kutusunun alt ortasına koyar",
    "Non-uniform or mirrored scale was moved into the mesh to keep the shape: %s":
        "Şekil bozulmasın diye eşit olmayan ya da aynalı ölçek mesh'e aktarıldı: %s",
    "Mesh shared with other objects, skipped: %s": "Mesh başka objelerle paylaşılıyor, atlandı: %s",
    "The axes already point that way": "Eksenler zaten o yöne bakıyor",
    "Origin axes aligned": "Origin eksenleri hizalandı",
    "Origin axes aligned on %d objects": "%d objede origin eksenleri hizalandı",
    "Rotation is animated, skipped: %s": "Dönüş animasyonlu, atlandı: %s",
    "Nothing selected on: %s": "Seçim yok: %s",
    "No clear direction in the shape of: %s": "Şeklinde belirgin bir yön yok: %s",
    "Select the objects to turn, then the one to copy last (active)":
        "Önce döndürülecek objeleri, en son eksenleri alınacak objeyi (aktif) seç",
    "Run it from a 3D View to use the view": "Görünümü kullanmak için 3D görünümden çalıştır",
    "Nothing to fix": "Düzeltilecek bir şey yok",
    "Ctrl+Q does not quit Blender (Origin Tools). Use File > Quit":
        "Ctrl+Q Blender'ı kapatmaz (Origin Tools). Çıkmak için File > Quit",
    "Ctrl Q is Origin to Selection over the 3D View. Elsewhere it does nothing, so Blender is never closed by "
    "accident (quit with File > Quit; this shortcut can be switched off in the add-on preferences)":
        "Ctrl Q, 3D görünümde Origin'i Seçime Taşı'dır. Başka yerlerde hiçbir şey yapmaz, böylece Blender yanlışlıkla "
        "kapanmaz (çıkmak için File > Quit; bu kısayol eklenti tercihlerinden kapatılabilir)",
    "Scale is animated, skipped: %s": "Ölçek animasyonlu, atlandı: %s",
    "Scale applied on %d objects": "%d objede ölçek uygulandı",
}


def _translation_dict():
    table = {}
    for source, target in TR_UI.items():
        table[(I18N_CTX, source)] = target
    for context in (I18N_CTX, "*", "Operator"):
        for source, target in TR_TEXT.items():
            table[(context, source)] = target
    return {"tr_TR": table}


def register(name):
    bpy.app.translations.register(name, _translation_dict())


def unregister(name):
    bpy.app.translations.unregister(name)
