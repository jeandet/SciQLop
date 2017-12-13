#ifndef SCIQLOP_CATALOGUETREEWIDGETITEM_H
#define SCIQLOP_CATALOGUETREEWIDGETITEM_H

#include <Common/spimpl.h>
#include <QTreeWidgetItem>

class DBCatalogue;


class CatalogueTreeWidgetItem : public QTreeWidgetItem {
public:
    CatalogueTreeWidgetItem(std::shared_ptr<DBCatalogue> catalogue,
                            int type = QTreeWidgetItem::Type);

    QVariant data(int column, int role) const override;
    void setData(int column, int role, const QVariant &value) override;

    /// Returns the catalogue represented by the item
    std::shared_ptr<DBCatalogue> catalogue() const;

    void setHasChanges(bool value);

private:
    class CatalogueTreeWidgetItemPrivate;
    spimpl::unique_impl_ptr<CatalogueTreeWidgetItemPrivate> impl;
};

#endif // SCIQLOP_CATALOGUETREEWIDGETITEM_H
